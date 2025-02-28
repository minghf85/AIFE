from numpy import full
from openai import OpenAI
from PyQt6.QtCore import QThread, pyqtSignal
from TTS import TTSThread
import os

class LLMThread(QThread):
    response_text_received = pyqtSignal(str)
    response_full_text_received = pyqtSignal(str)
    response_started = pyqtSignal()
    response_finished = pyqtSignal()

    def __init__(self, model, prompt, message,basettsurl, tts_settings=None):
        super().__init__()
        self.model = model
        self.prompt = prompt
        self.message = message
        self.tts_settings = tts_settings
        self.basettsurl = basettsurl
        self.tts_thread = TTSThread(baseurl=self.basettsurl,tts_settings=self.tts_settings) if self.tts_settings else None
        self.history_messages = []
        self.interrupted = False
        self.current_response = ""
    
    def interrupt(self):
        """打断当前生成"""
            
        self.interrupted = True
        if self.tts_thread:
            self.tts_thread.stop()
        
        # 如果有已生成的内容，保存到历史记录
        if self.current_response:
            self.history_messages.append({
                'role': 'assistant',
                'content': self.current_response
            })
    
    def run(self):
        try:
            self.interrupted = False
            self.current_response = ""
            
            if self.tts_thread:
                self.tts_thread.start()
                
            # 初始化或更新历史消息
            if not self.history_messages:   
                self.history_messages = [
                    {'role': 'system', 'content': self.prompt},
                    {'role': 'user', 'content': self.message}
                ]
            else:
                # 添加新的用户消息
                self.history_messages.append({'role': 'user', 'content': self.message})
            
            client = OpenAI(
                api_key='ollama', 
                base_url="http://localhost:11434/v1/"
            ) if self.model != "deepseek-chat" else OpenAI(
                api_key=os.getenv('DEEPSEEK_API_KEY'),
                base_url="https://api.deepseek.com/v1"
            )
            
            response = client.chat.completions.create(
                model=self.model,
                messages=self.history_messages,
                stream=True
            )
            
            current_segment = ""
            first_sentence_in = True
            self.response_started.emit()
            
            for chunk in response:
                if self.interrupted:
                    print("生成被打断")
                    break
                    
                content = chunk.choices[0].delta.content
                    
                self.current_response += content
                self.response_text_received.emit(content)
                current_segment += content
                if self.tts_thread:
                    if chunk.choices[0].finish_reason == "stop":
                        self.tts_thread.add_text(current_segment)
                        current_segment = ""
                    if len(current_segment) < 8:
                        continue
                    '''[
                        # 英文
                        '.', '?', '!', ';', ':',
                        # 中文
                        '。', '？', '！', '；', '：',
                        # 法语
                        '»', '«',
                        # 西班牙语
                        '¿', '¡',
                        # 其他
                        '…', '...', '——','···'
                    ]'''
                    if any(current_segment.endswith(p) for p in [
                        # 英文
                        '.', '?', '!', ';', ':',
                        # 中文
                        '。', '？', '！', '；', '：',
                        # 法语
                        '»', '«',
                        # 西班牙语
                        '¿', '¡',
                        # 其他
                        '…', '...', '——','···'
                    ]):
                        if first_sentence_in:
                            self.tts_thread.add_text("." + current_segment)
                            first_sentence_in = False
                        else:
                            self.tts_thread.add_text(current_segment)
                        current_segment = ""
            
            # 如果没有被打断，将完整响应添加到历史记录
            if not self.interrupted:
                self.history_messages.append({
                    'role': 'assistant',
                    'content': self.current_response
                })
            
            self.response_finished.emit()
            
        except Exception as e:
            if self.tts_settings:
                self.response_full_text_received.emit(f"错误：{str(e)}")
            else:
                self.response_text_received.emit(f"错误: {str(e)}")
            