from PyQt6.QtCore import QThread, pyqtSignal
from RealtimeSTT import AudioToTextRecorder

class STTThread(QThread):
    text_signal = pyqtSignal(str)
    test_signal = pyqtSignal(str)
    STTmodel_ready_signal = pyqtSignal()

    def __init__(self, config):
        super().__init__()
        # 添加实时转录相关配置
        self.config = config.copy()
        self.config.update({
            'on_realtime_transcription_update': self.process_text  # 实时转录回调
        })
        self.running = True
        self.is_testing = False
        self.recorder = None
        self.paused = True
        self.last_text = ""
        self.chat_window = None

    def set_chat_window(self, chat_window):
        """设置聊天窗口引用"""
        self.chat_window = chat_window

    def run(self):
        try:
            if not self.recorder:
                # 创建录音器
                self.recorder = AudioToTextRecorder(**self.config)
                
                # 等待 recorder.is_running 变为 True
                while not self.recorder.is_running:
                    if not self.running:
                        return
                    self.msleep(100)
                
                # 发送模型就绪信号
                self.STTmodel_ready_signal.emit()
            
                # 开始录音和识别循环
                while self.running:
                    if not self.paused:
                        # 获取识别结果
                        result = self.recorder.text()
                        # 如果不是测试模式且有chat_window，则更新输入框
                        if result and not self.is_testing and self.chat_window and self.chat_window.voice_input_enabled and not self.chat_window.user_editing:
                            self.chat_window.sendMessage(result)
                    else:
                        self.msleep(100)
                
        except Exception as e:
            print(f"Error in STT Thread: {e}")

    def process_text(self, text):
        """处理实时转录的文本"""
        if text != self.last_text and not self.is_testing:
            self.last_text = text
            # 发送文本用于显示
            self.text_signal.emit(text)
        elif text != self.last_text and self.is_testing:
            self.last_text = text
            self.test_signal.emit(text)

    def pause(self):
        """暂停录音"""
        if self.recorder:
            self.paused = True
            self.recorder.stop()

    def resume(self):
        """恢复录音"""
        self.paused = False

    def stop(self):
        """停止线程"""
        self.running = False
        if self.recorder:
            self.recorder.stop()
        self.wait()
