import numpy as np
import threading
import time
from live2d.utils.lipsync import WavHandler

class MicLipSync:
    def __init__(self):
        self.is_running = False
        self.wav_handler = WavHandler()
        self.current_rms = 0.0
        self.tts_player = None  # 用于存储TTS的AudioPlayer实例
        
    def set_tts_player(self, player):
        """设置TTS播放器实例"""
        self.tts_player = player
        
    def start(self):
        """开始口型同步"""
        if self.is_running:
            return
            
        self.is_running = True
        self.current_rms = 0.0
        
    def stop(self):
        """停止口型同步"""
        self.is_running = False
        self.current_rms = 0.0
            
    def get_rms(self) -> float:
        """获取当前RMS值"""
        if not self.is_running or not self.tts_player:
            return 0.0
            
        # 从音频数据计算RMS值
        try:
            if self.tts_player.is_playing:
                with self.tts_player.cache_lock:
                    if self.tts_player.audio_cache:
                        audio_data = self.tts_player.audio_cache[0]  # 只读取不移除
                        audio_array = np.frombuffer(audio_data, dtype=np.int16)
                        rms = np.sqrt(np.mean(np.square(audio_array.astype(np.float32) / 32768.0)))
                        self.current_rms = min(1.0, rms * 2)  # 可以调整系数来改变灵敏度
                        return self.current_rms
        except Exception as e:
            print(f"计算RMS值时出错: {e}")
            
        return self.current_rms
        
    def update(self) -> bool:
        """更新并返回是否继续"""
        return self.is_running
