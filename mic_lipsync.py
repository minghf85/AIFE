import pyaudio
import wave
import tempfile
import os
import threading
import time
import numpy as np
from live2d.utils.lipsync import WavHandler

class MicLipSync:
    def __init__(self):
        self.p = pyaudio.PyAudio()
        self.stream = None
        self.is_running = False
        self.wav_handler = WavHandler()
        self.thread = None
        self.temp_wav = None
        self.frames = []
        self.current_rms = 0.0
        
        # 音频参数
        self.CHUNK = 1024
        self.FORMAT = pyaudio.paInt16
        self.CHANNELS = 1
        self.RATE = 44100
        self.selected_device_index = None
        
    def get_input_devices(self):
        """获取所有输入设备"""
        devices = []
        for i in range(self.p.get_device_count()):
            device_info = self.p.get_device_info_by_index(i)
            if device_info['maxInputChannels'] > 0:  # 只获取输入设备
                devices.append({
                    'index': i,
                    'name': device_info['name'],
                    'channels': device_info['maxInputChannels'],
                    'sample_rate': int(device_info['defaultSampleRate'])
                })
        return devices
        
    def select_device(self, device_index: int):
        """选择输入设备"""
        self.selected_device_index = device_index
        device_info = self.p.get_device_info_by_index(device_index)
        self.CHANNELS = min(device_info['maxInputChannels'], 2)  # 最多使用2个通道
        self.RATE = int(device_info['defaultSampleRate'])
        
    def _audio_callback(self, in_data, frame_count, time_info, status):
        """音频回调函数"""
        if self.is_running:
            # 将字节数据转换为numpy数组
            audio_data = np.frombuffer(in_data, dtype=np.int16)
            
            # 计算RMS值
            self.current_rms = np.sqrt(np.mean(np.square(audio_data.astype(np.float32) / 32768.0)))
            
            # 将RMS值标准化到0-1范围
            self.current_rms = min(1.0, self.current_rms * 2)  # 可以调整系数来改变灵敏度
                
        return (in_data, pyaudio.paContinue)
        
    def start(self):
        """开始录音和口型同步"""
        if self.is_running:
            return
            
        if self.selected_device_index is None:
            raise ValueError("No input device selected")
            
        self.is_running = True
        self.current_rms = 0.0
        
        # 创建音频流
        self.stream = self.p.open(
            format=self.FORMAT,
            channels=self.CHANNELS,
            rate=self.RATE,
            input=True,
            input_device_index=self.selected_device_index,
            frames_per_buffer=self.CHUNK,
            stream_callback=self._audio_callback
        )
        
        # 启动音频流
        self.stream.start_stream()
        
    def stop(self):
        """停止录音和口型同步"""
        self.is_running = False
        
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
            self.stream = None
            
        self.current_rms = 0.0
            
    def get_rms(self) -> float:
        """获取当前RMS值"""
        return self.current_rms
        
    def update(self) -> bool:
        """更新并返回是否继续"""
        return self.is_running
        
    def __del__(self):
        """清理资源"""
        self.stop()
        if self.p:
            self.p.terminate()
