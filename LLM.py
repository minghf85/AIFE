from openai import OpenAI
from PyQt6.QtCore import QThread, pyqtSignal
from TTS import TTSThread
import os
class LLMThread(QThread):
    response_text_received = pyqtSignal(str)
    response_full_text_received = pyqtSignal(str)
    
    def __init__(self, model, prompt, message, tts_settings=None):
        super().__init__()
        self.model = model
        self.prompt = prompt
        self.message = message
        self.tts_settings = tts_settings
        self.tts_thread = TTSThread(self.tts_settings) if self.tts_settings else None

    def run(self):
        try:
            if self.tts_thread:
                self.tts_thread.start()
            client = OpenAI(api_key='ollama', base_url="http://localhost:11434/v1/") if self.model!="deepseek-chat" else OpenAI(api_key=os.getenv('DEEPSEEK_API_KEY'),base_url="https://api.deepseek.com/v1")
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {'role': 'system', 'content': self.prompt},
                    {'role': 'user', 'content': self.message}
                ],
                stream=True
            )
            current_segment = ""
            first_sentence_in = True
            for chunk in response:
                if chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    self.response_text_received.emit(content)
                    if self.tts_thread :
                        current_segment += content
                            
                            # 当遇到标点符号时，将文本加入队列
                        if any(p in current_segment for p in '。！？.!?'):
                            if first_sentence_in:
                                self.tts_thread.add_text("."+current_segment)
                                first_sentence_in = False
                            else:
                                self.tts_thread.add_text(current_segment)
                            current_segment = ""
            
        except Exception as e:
            if self.tts_settings:
                self.response_full_text_received.emit(f"错误：{str(e)}")
            else:
                self.response_text_received.emit(f"错误: {str(e)}")
            