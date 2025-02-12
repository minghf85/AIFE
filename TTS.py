import threading
from queue import Queue
from collections import deque
import pyaudio as pa
import time
import wave
import requests
import io
import os
from datetime import datetime

from requests.auth import CONTENT_TYPE_FORM_URLENCODED

class AudioPlayer:
    def __init__(self, play_device=None):
        self.running = True
        self.audio_cache = deque()
        self.cache_lock = threading.Lock()
        self.cache_event = threading.Event()
        self.p = pa.PyAudio()
        self.stream = None
        self.play_device = play_device
        self.setup_stream()
        self.error_count = 0
        self.max_errors = 3
        self.is_playing = False
        self.last_play_time = time.time()
        self.total_played = 0
        self.saved_audio = bytearray()  # 用于保存音频数据
        self.save_audio = False  # 是否保存音频数据的标志
        
    def setup_stream(self):
        try:
            if self.stream is not None:
                self.stream.stop_stream()
                self.stream.close()
            
            self.stream = self.p.open(
                format=self.p.get_format_from_width(2),
                channels=1,
                rate=32000,
                output=True,
                output_device_index=self.play_device
            )
        except Exception as e:
            print(f"设置音频流时出错: {e}")
            
    def add_audio_data(self, audio_data):
        with self.cache_lock:
            self.audio_cache.append(audio_data)
            if self.save_audio:
                self.saved_audio.extend(audio_data)
        self.cache_event.set()
        
    def get_cache_size(self):
        with self.cache_lock:
            return len(self.audio_cache)
            
    def run(self):
        while self.running:
            try:
                if not self.audio_cache:
                    self.cache_event.wait(timeout=0.1)
                    self.cache_event.clear()
                    continue
                    
                with self.cache_lock:
                    if not self.audio_cache:
                        continue
                    audio_data = self.audio_cache.popleft()
                
                if audio_data:
                    self.stream.write(audio_data)
                    self.is_playing = True
                    self.last_play_time = time.time()
                    self.total_played += len(audio_data)
                else:
                    self.is_playing = False
                    
            except Exception as e:
                print(f"音频播放错误: {e}")
                self.error_count += 1
                if self.error_count >= self.max_errors:
                    print("错误次数过多，重新设置音频流")
                    self.setup_stream()
                    self.error_count = 0
                time.sleep(0.1)
                
    def stop(self):
        self.running = False
        try:
            if self.stream is not None:
                self.stream.stop_stream()
                self.stream.close()
        except Exception as e:
            print(f"关闭音频流时出错: {e}")
        self.p.terminate()
        
    def wait_for_cache_empty(self):
        while self.get_cache_size() > 0:
            time.sleep(0.1)

    def clear(self):
        """清理所有音频缓存并重置音频流"""
        with self.cache_lock:
            self.audio_cache.clear()
        if self.stream:
            try:
                self.stream.stop_stream()
                self.stream.close()
                self.stream = None
                self.setup_stream()  # 重新初始化音频流
            except Exception as e:
                print(f"重置音频流时出错: {e}")
        self.is_playing = False
        self.cache_event.clear()

class TTSThread:
    def __init__(self, baseurl,tts_settings, stream=None, play_device=None, save_wav=False):
        """
        初始化实时TTS系统
        :param tts_settings: TTS设置，包含所有必要的参数
        :param stream: 文本流，用于实时生成文本
        :param play_device: 播放设备索引，默认为None使用系统默认设备
        :param save_wav: 是否保存音频文件
        """
        self.baseurl = baseurl
        self.tts_settings = tts_settings
        self.stream = stream
        self.text_queue = Queue()
        self.running = False
        self.audio_player = AudioPlayer(play_device)
        self.audio_thread = None
        self.tts_thread = None
        self.stream_thread = None
        # 检查是否有初始文本需要处理
        self.initial_text = self.tts_settings.get("text")
        self.full_text = self.initial_text
        self.content = ""
        self.save_wav = save_wav
        self.text_ready = threading.Event()  # 添加事件标志
        
        # 如果需要保存音频，创建保存目录
        if self.save_wav:
            self.audio_dir = os.path.join("logs", "audio")
            os.makedirs(self.audio_dir, exist_ok=True)
            self.audio_player.save_audio = True

    def _save_current_audio(self):
        """保存当前音频"""
        if not self.save_wav or not self.audio_player.saved_audio:
            return
            
        try:
            # 生成文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = os.path.join(self.audio_dir, f"tts_{timestamp}.wav")
            
            # 创建WAV文件
            with wave.open(filename, 'wb') as wf:
                wf.setnchannels(1)  # 单声道
                wf.setsampwidth(2)  # 16位采样
                wf.setframerate(32000)  # 采样率
                wf.writeframes(self.audio_player.saved_audio)
            print(f"音频已保存到: {filename}")
            
            # 清理已保存的音频数据
            self.audio_player.saved_audio = bytearray()
            
        except Exception as e:
            print(f"保存音频失败: {e}")
            
    def process_text(self):
        """处理文本并生成音频"""
        # 如果有初始文本，先处理它
        if self.initial_text and self.running:
            print(f"处理初始文本: {self.initial_text}")
            self._synthesize_text(self.initial_text)
            self.initial_text = None  # 清除初始文本，避免重复处理
        
        while self.running:
            try:
                if not self.text_queue.empty():
                    text = self.text_queue.get()
                    if text:
                        self._synthesize_text(text)
            except Exception as e:
                print(f"TTS处理错误: {e}")
                time.sleep(1)
            time.sleep(0.001)
            
    def _synthesize_text(self, text):
        """合成单个文本并播放"""
        try:
            print(f"正在合成文本: {text}")
            # 保存当前设置中的文本
            original_text = self.tts_settings.get("text")
            
            # 设置要合成的文本
            self.tts_settings["text"] = text
            
            # 发送请求
            response = requests.post(
                f"{self.baseurl}/tts",
                json=self.tts_settings,
                stream=True,
                headers={'Accept': 'audio/x-wav'}
            )
            
            if response.status_code == 200:
                first_chunk = True
                for chunk in response.iter_content(chunk_size=1024):
                    if not self.running:
                        break
                        
                    if chunk:
                        if first_chunk and chunk.startswith(b'RIFF'):
                            chunk = chunk[44:]
                            first_chunk = False
                        
                        if len(chunk) > 0:
                            if self.save_wav:
                                self.audio_player.save_audio = True
                            self.audio_player.add_audio_data(chunk)
                            
                print(f"文本合成完成: {text}")
                
                # 如果不是流式输入，保存当前音频
                if not self.stream and self.save_wav:
                    print("保存音频...")
                    self._save_current_audio()
                    
            else:
                print(f"语音合成失败: {response.text}")
                
            # 恢复原始文本设置
            self.tts_settings["text"] = original_text
            
        except Exception as e:
            print(f"处理文本时出错: {e}")
            
    def process_stream(self):
        """处理文本流"""
        if not self.stream:
            return
            
        current_segment = ""
        first_sentence_in = True
        for chunk in self.stream:
            if not self.running:
                break
            

            if chunk.choices[0].delta.constent:
                content = chunk.choices[0].delta.content
                self.full_text += content
                current_segment += content
                if chunk.choices[0].finish_reason == "stop":
                    self.text_queue.put(current_segment)
                    current_segment = ""
                if len(current_segment)<6:
                    continue
                        # 当遇到标点符号时，将文本加入队列
                if any(current_segment.endswith(p) for p in '，,。！？.!?~'):
                    if first_sentence_in:
                        self.text_queue.put("."+current_segment)
                        first_sentence_in = False
                    else:
                        self.text_queue.put(current_segment)
                    current_segment = ""
                    
        # 处理最后剩余的文本
        if current_segment and self.running:
            self.text_queue.put(current_segment)
            
        # 等待所有文本处理完成
        while not self.text_queue.empty() and self.running:
            time.sleep(0.1)
            
        # 等待音频处理和播放完成
        time.sleep(1.0)  # 增加等待时间
        
        # 等待音频缓存处理完成
        self.audio_player.wait_for_cache_empty()
        
        # 再等待一小段时间确保音频完全处理完成
        time.sleep(0.5)
            
        # 如果是流式输入，保存完整音频
        if self.save_wav and self.audio_player.saved_audio:
            print("保存流式合成的完整音频...")
            self._save_current_audio()
            
        # 设置文本准备完成标志
        self.text_ready.set()
            
    def get_full_text(self):
        """等待并获取完整文本"""
        self.text_ready.wait()  # 等待文本准备完成
        return self.full_text
        
    def start(self):
        """启动TTS系统"""
        if self.running:
            return
            
        self.running = True
        
        # 启动TTS线程
        self.tts_thread = threading.Thread(target=self.process_text)
        self.tts_thread.daemon = True
        self.tts_thread.start()
        
        # 如果有文本流，启动流处理线程
        if self.stream:
            self.stream_thread = threading.Thread(target=self.process_stream)
            self.stream_thread.daemon = True
            self.stream_thread.start()
            
        # 清理之前的音频数据
        self.audio_player.saved_audio = bytearray()
        
        # 启动音频播放线程
        self.audio_thread = threading.Thread(target=self.audio_player.run)
        self.audio_thread.daemon = True
        self.audio_thread.start()
        
        print(f"音频保存状态: {'启用' if self.save_wav else '禁用'}")
        if self.save_wav:
            print(f"音频保存目录: {self.audio_dir}")
            
    def stop(self):
        """停止TTS系统"""
        print("正在停止TTS系统...")
        
        # 首先设置运行状态为False
        self.running = False
        requests.get(f"{self.baseurl}/interrupt")
        # 立即清空文本队列
        while not self.text_queue.empty():
            try:
                self.text_queue.get_nowait()
            except:
                pass
        
        # 完全清理和重置音频播放器
        if self.audio_player:
            self.audio_player.clear()
        
        # 确保在停止前保存音频
        if self.save_wav and self.audio_player.saved_audio:
            print("停止前保存音频...")
            self._save_current_audio()
            
        # 完全停止音频播放器
        if self.audio_player:
            self.audio_player.stop()
            
        # 等待线程结束
        if self.audio_thread:
            self.audio_thread.join(timeout=1.0)
        if self.tts_thread:
            self.tts_thread.join(timeout=1.0)
        if self.stream_thread:
            self.stream_thread.join(timeout=1.0)
            
    def add_text(self, text):
        """添加文本到队列"""
        if self.running:
            self.text_queue.put(text)
