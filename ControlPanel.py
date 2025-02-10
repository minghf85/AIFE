import json
import re
from PyQt6.QtWidgets import (QApplication, QMainWindow, QPushButton, QVBoxLayout, 
                           QHBoxLayout, QWidget, QFileDialog, QLabel, QComboBox,
                           QGroupBox,  QMessageBox, QSlider, QTabWidget,QSpinBox,
                           QTextEdit, QPlainTextEdit, QLineEdit, QDoubleSpinBox, QGridLayout,QCheckBox)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from OpenGL.GL import *
from standardize import standardize_model
from TTS import TTSThread
from STT import STTThread
from LLM import LLMThread
import pyaudio as pa
import ollama
import random

STYLE_SHEET = """
QMainWindow {
    background-color: #FFFFFF;
}

QWidget {
    color: #333333;
    font-family: 'Segoe UI', sans-serif;
}

QPushButton {
    background-color: #4FB4FF;
    border: none;
    border-radius: 10px;
    padding: 8px 16px;
    color: white;
    font-size: 14px;
    margin: 2px;
}

QPushButton:hover {
    background-color: #1E90FF;
}

QPushButton:pressed {
    background-color: #0000FF;
}

QPushButton:disabled {
    background-color: #B8E2FF;
    color: #888888;
}

QComboBox {
    background-color: #4FB4FF;
    border: none;
    border-radius: 10px;
    padding: 8px;
    color: white;
    min-width: 150px;
    selection-background-color: #69C0FF;
}

QComboBox:hover {
    background-color: #69C0FF;
}

QComboBox::drop-down {
    border: none;
    width: 20px;
}

QComboBox::down-arrow {
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 5px solid white;
    margin-right: 8px;
}

QComboBox QAbstractItemView {
    background-color: #4FB4FF;
    border: none;
    selection-background-color: #69C0FF;
    selection-color: white;
    color: white;
    outline: 0px;
}

QGroupBox {
    border: 2px solid #4FB4FF;
    border-radius: 15px;
    margin-top: 10px;
    padding-top: 15px;
    font-size: 14px;
    background-color: #FFFFFF;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top center;
    padding: 0 10px;
    color: #333333;
    background-color: #FFFFFF;
}

QLabel {
    color: #333333;
    font-size: 14px;
}

QScrollBar:vertical {
    border: none;
    background-color: #F0F0F0;
    width: 10px;
    margin: 0px;
}

QScrollBar::handle:vertical {
    background-color: #4FB4FF;
    border-radius: 5px;
    min-height: 20px;
}

QScrollBar::handle:vertical:hover {
    background-color: #69C0FF;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: none;
}
"""

class ControlPanel(QMainWindow):
    def __init__(self, live2d_window):
        super().__init__()
        self.live2d_window = live2d_window
        self.subtitle_window = SubtitleWindow()
        self.STT_thread = None
        self.chat_tts_thread = None
        self.test_tts = None
        self.subtitle_visible = False
        self.tts_settings = {
            "text": "",
            "text_lang": "zh",
            "ref_audio_path": "H:/AIVtuber/VOICE_reference/HAPPY.wav",
            "aux_ref_audio_paths": [],
            "prompt_text": "呵哼哼，想要拿到它的话，就先加油追上我吧。",
            "prompt_lang": "zh",
            "top_k": 5,
            "top_p": 1.0,
            "temperature": 1.0,
            "text_split_method": "cut0",
            "batch_size": 5,
            "batch_threshold": 0.75,
            "split_bucket": False,
            "return_fragment": False,
            "speed_factor": 1.0,
            "streaming_mode": False,
            "seed": -1,
            "parallel_infer": True,
            "repetition_penalty": 1.35
        }

        self.last_voice_text = ""
        self.voice_input_enabled = False
        self.voice_synthesis_enabled = False
        self.user_editing = False

        self.initUI()
        self.updateAudioDevices()
        self.updateLLMModels()
        
        # 初始化语音识别语言选项
        self.STT_language_combo.addItems(["zh", "en", "ja", "ko", "de", "fr"])
        
        # 在初始化完成后加载配置
        self.loadsettings()
        
    def updateLLMModels(self):
        model_names = []
        """更新Ollama模型列表"""
        try:
            models = ollama.list()
            model_names = [model['model'] for model in models['models']]
        except Exception as e:
            print(f"获取Ollama模型列表失败: {str(e)}")
        model_names.insert(0, "deepseek-chat")
        self.chat_model_combo.clear()
        self.chat_model_combo.addItems(model_names)
            
    def updateAudioDevices(self):
        """更新音频设备列表"""
        if not hasattr(self, 'audio_devices') or not hasattr(self, 'STT_audio_devices'):
            return
            
        self.audio_devices.clear()
        self.STT_audio_devices.clear()
        if hasattr(self, 'TTS_audio_devices'):
            self.TTS_audio_devices.clear()
        
        p = pa.PyAudio()
        try:
            for i in range(p.get_device_count()):
                try:
                    device_info = p.get_device_info_by_index(i)
                    device_name = device_info['name']
                    
                    # 为口型同步添加输入设备
                    if device_info['maxInputChannels'] > 0:
                        self.audio_devices.addItem(device_name, i)
                        # 为语音识别添加设备（包含索引）
                        self.STT_audio_devices.addItem(f"{i}: {device_name}", i)
                        
                    # 为TTS添加输出设备
                    if device_info['maxOutputChannels'] > 0:
                        self.TTS_audio_devices.addItem(f"{i}: {device_name}", i)
                except Exception as e:
                    print(f"获取音频设备信息失败: {str(e)}")
        finally:
            p.terminate()
            
        # 如果有设备，默认选择第一个
        if self.STT_audio_devices.count() > 0:
            self.STT_audio_devices.setCurrentIndex(0)
        if self.TTS_audio_devices.count() > 0:
            self.TTS_audio_devices.setCurrentIndex(0)
            
    def initUI(self):
        """初始化UI"""
        # 设置窗口标题和大小
        self.setWindowTitle('Live2D 控制面板')
        self.setGeometry(100, 100, 400, 400)
        
        # 创建中心部件和主布局
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(10)
        
        # 创建选项卡
        tab_widget = QTabWidget()
        main_layout.addWidget(tab_widget)
        
        # === 模型控制选项卡 ===
        model_tab = QWidget()
        model_layout = QVBoxLayout(model_tab)
        
        # 模型加载部分
        model_group = QGroupBox("模型控制")
        model_group_layout = QVBoxLayout()
        
        # 标准化模型按钮
        self.standardize_btn = QPushButton('标准化模型', self)
        self.standardize_btn.clicked.connect(self.standardizeModel)
        model_group_layout.addWidget(self.standardize_btn)
        
        # 模型选择按钮
        self.model_btn = QPushButton('选择模型文件', self)
        self.model_btn.clicked.connect(self.loadModel)
        model_group_layout.addWidget(self.model_btn)
        
        # 卸载模型按钮
        self.unload_live2dmodel_btn = QPushButton('卸载模型', self)
        self.unload_live2dmodel_btn.clicked.connect(self.unloadModel)
        self.unload_live2dmodel_btn.setEnabled(False)
        model_group_layout.addWidget(self.unload_live2dmodel_btn)
        
        # 动作控制
        model_group_layout.addWidget(QLabel("动作组:"))
        self.motion_group_combo = QComboBox(self)
        self.motion_group_combo.currentIndexChanged.connect(self.updateMotionList)
        self.motion_group_combo.setEnabled(False)
        model_group_layout.addWidget(self.motion_group_combo)
        
        model_group_layout.addWidget(QLabel("动作:"))
        self.motion_combo = QComboBox(self)
        self.motion_combo.setEnabled(False)
        model_group_layout.addWidget(self.motion_combo)
        
        # 开启随机播放动作
        self.play_random_motion_btn = QPushButton('开启随机播放动作', self)
        self.play_random_motion_btn.setCheckable(True)
        self.play_random_motion_btn.clicked.connect(self.toggleplayrandomMotion)
        self.play_random_motion_btn.setEnabled(False)
        model_group_layout.addWidget(self.play_random_motion_btn)
        
        # 播放动作按钮
        self.play_motion_btn = QPushButton('播放动作', self)
        self.play_motion_btn.clicked.connect(self.playMotion)
        self.play_motion_btn.setEnabled(False)
        model_group_layout.addWidget(self.play_motion_btn)
        
        # 表情选择
        model_group_layout.addWidget(QLabel("表情:"))
        self.expression_combo = QComboBox(self)
        self.expression_combo.currentTextChanged.connect(self.changeExpression)
        self.expression_combo.setEnabled(False)
        model_group_layout.addWidget(self.expression_combo)

        #随机表情
        self.play_random_expression_btn = QPushButton('开启随机表情', self)
        self.play_random_expression_btn.setCheckable(True)
        self.play_random_expression_btn.clicked.connect(self.toggleplayrandomExpression)
        self.play_random_expression_btn.setEnabled(False)
        model_group_layout.addWidget(self.play_random_expression_btn)
        
        model_group.setLayout(model_group_layout)
        model_layout.addWidget(model_group)
        model_layout.addStretch()
        
        # === 视线跟踪选项卡 ===
        tracking_tab = QWidget()
        tracking_layout = QVBoxLayout(tracking_tab)
        
        # 视线跟踪控制组
        tracking_group = QGroupBox("视线跟踪设置")
        tracking_group_layout = QVBoxLayout()
        
        # 视线跟踪开关
        self.eye_tracking_btn = QPushButton('开启视线跟踪', self)
        self.eye_tracking_btn.setCheckable(True)
        self.eye_tracking_btn.clicked.connect(self.toggleEyeTracking)
        self.eye_tracking_btn.setEnabled(False)
        tracking_group_layout.addWidget(self.eye_tracking_btn)
        
        # 跟随强度滑块
        self.eye_tracking_strength_slider = QSlider(Qt.Orientation.Horizontal)
        self.eye_tracking_strength_slider.setMinimum(0)
        self.eye_tracking_strength_slider.setMaximum(100)
        self.eye_tracking_strength_slider.setValue(50)
        self.eye_tracking_strength_slider.valueChanged.connect(self.updateEyeTrackingStrength)
        self.eye_tracking_strength_slider.setEnabled(False)
        tracking_group_layout.addWidget(QLabel("跟随强度:"))
        tracking_group_layout.addWidget(self.eye_tracking_strength_slider)
        
        tracking_group.setLayout(tracking_group_layout)
        tracking_layout.addWidget(tracking_group)
        tracking_layout.addStretch()
        
        # === 口型同步选项卡 ===
        lipsync_tab = QWidget()
        lipsync_layout = QVBoxLayout(lipsync_tab)
        
        # 口型同步控制组
        lipsync_group = QGroupBox("口型同步设置")
        lipsync_group_layout = QVBoxLayout()
        
        # 音频设备选择
        self.audio_devices = QComboBox(self)
        self.audio_devices.setEnabled(True)
        lipsync_group_layout.addWidget(QLabel("选择音频设备:"))
        lipsync_group_layout.addWidget(self.audio_devices)
        
        # 口型同步开关
        self.lip_sync_btn = QPushButton('开启口型同步')
        self.lip_sync_btn.setCheckable(True)
        self.lip_sync_btn.clicked.connect(self.toggleLipSync)
        self.lip_sync_btn.setEnabled(False)
        lipsync_group_layout.addWidget(self.lip_sync_btn)
        
        # 同步强度滑块
        self.lip_sync_strength = QSlider(Qt.Orientation.Horizontal)
        self.lip_sync_strength.setMinimum(0)
        self.lip_sync_strength.setMaximum(100)
        self.lip_sync_strength.setValue(30)
        self.lip_sync_strength.valueChanged.connect(self.updateLipSyncStrength)
        self.lip_sync_strength.setEnabled(False)
        lipsync_group_layout.addWidget(QLabel("同步强度:"))
        lipsync_group_layout.addWidget(self.lip_sync_strength)
        
        lipsync_group.setLayout(lipsync_group_layout)
        lipsync_layout.addWidget(lipsync_group)
        lipsync_layout.addStretch()
        
        # === 语音识别选项卡 ===
        STT_tab = QWidget()
        STT_layout = QVBoxLayout(STT_tab)
        
        # 语音识别设置组
        STT_group = QGroupBox("语音识别设置")
        STT_group_layout = QVBoxLayout()
        
        # 麦克风选择
        STT_group_layout.addWidget(QLabel("选择麦克风:"))
        self.STT_audio_devices = QComboBox(self)
        self.STT_audio_devices.setEnabled(True)  # 启用麦克风选择
        STT_group_layout.addWidget(self.STT_audio_devices)

        # 目标识别语言
        STT_group_layout.addWidget(QLabel("目标识别语言:"))
        self.STT_language_combo = QComboBox()
        self.STT_language_combo.setEnabled(True)  # 启用语言选择
        STT_group_layout.addWidget(self.STT_language_combo)

        # 模型选择
        STT_group_layout.addWidget(QLabel("选择模型:"))
        self.STT_model_combo = QComboBox()
        self.STT_model_combo.addItems(["tiny", "tiny.en", "base", "base.en", "small", "small.en", 
                                 "medium", "medium.en", "large-v1", "large-v2","large-v3","large-v3 turbo"])
        STT_group_layout.addWidget(self.STT_model_combo)
        
        # 唤醒词 可以自定义
        STT_group_layout.addWidget(QLabel("唤醒词(暂不可用X):"))
        self.STT_wake_word_edit = QPlainTextEdit()
        self.STT_wake_word_edit.setMaximumHeight(100)
        self.STT_wake_word_edit.setPlaceholderText("输入唤醒词...")
        STT_group_layout.addWidget(self.STT_wake_word_edit)

        # 加载模型
        self.load_STTmodel_btn = QPushButton("加载模型")
        self.load_STTmodel_btn.clicked.connect(self.loadSTTModel)
        STT_group_layout.addWidget(self.load_STTmodel_btn)

        # 卸载模型
        self.unload_STTmodel_btn = QPushButton("卸载模型")
        self.unload_STTmodel_btn.clicked.connect(self.unloadSTTModel)
        self.unload_STTmodel_btn.setEnabled(False)
        STT_group_layout.addWidget(self.unload_STTmodel_btn)

        # 测试模型 这一部分是测试语音识别功能，只有在模型加载成功之后使能这个按钮，开启后字样变为关闭测试，然后会将选择的麦克风识别到的文字流式输出到一个文本框内
        self.test_STT_btn = QPushButton("开始测试")
        self.test_STT_btn.clicked.connect(self.testSTTModel)
        self.test_STT_btn.setEnabled(False)
        STT_group_layout.addWidget(self.test_STT_btn)

        # 识别结果
        STT_group_layout.addWidget(QLabel("测试识别结果:"))
        self.test_STT_result_label = QLabel()
        STT_group_layout.addWidget(self.test_STT_result_label)

        STT_group.setLayout(STT_group_layout)
        STT_layout.addWidget(STT_group)
        STT_layout.addStretch()
        # === 语音生成选项卡 ===
        TTS_tab = QWidget()
        TTS_layout = QVBoxLayout(TTS_tab)
        
        # 语音生成设置组
        TTS_group = QGroupBox("语音生成设置")
        TTS_group_layout = QVBoxLayout()
        
        # 参考音频路径
        ref_audio_layout = QHBoxLayout()
        ref_audio_label = QLabel("参考音频:")
        self.ref_audio_path = QLineEdit("H:/AIVtuber/VOICE_reference/HAPPY.wav")
        self.ref_audio_path.setReadOnly(True)
        ref_audio_btn = QPushButton("选择文件")
        ref_audio_btn.clicked.connect(self.selectRefAudio)
        ref_audio_layout.addWidget(ref_audio_label)
        ref_audio_layout.addWidget(self.ref_audio_path)
        ref_audio_layout.addWidget(ref_audio_btn)
        TTS_group_layout.addLayout(ref_audio_layout)
        
        # 辅助参考音频路径
        aux_ref_layout = QHBoxLayout()
        aux_ref_label = QLabel("辅助参考:")
        self.aux_ref_list = QTextEdit()
        self.aux_ref_list.setMaximumHeight(60)
        self.aux_ref_list.setReadOnly(True)
        aux_ref_btn = QPushButton("选择文件")
        aux_ref_btn.clicked.connect(self.selectAuxRefAudio)
        aux_ref_layout.addWidget(aux_ref_label)
        aux_ref_layout.addWidget(self.aux_ref_list)
        aux_ref_layout.addWidget(aux_ref_btn)
        TTS_group_layout.addLayout(aux_ref_layout)
        
        # 语言选择
        lang_layout = QGridLayout()
        # 文本语言
        text_lang_label = QLabel("文本语言:")
        self.text_lang_combo = QComboBox()
        self.text_lang_combo.addItems(["zh", "en", "ja", "ko"])
        self.text_lang_combo.setCurrentText(self.tts_settings["text_lang"])
        self.text_lang_combo.currentTextChanged.connect(lambda x: self.updateTTSSetting("text_lang", x))
        lang_layout.addWidget(text_lang_label, 0, 0)
        lang_layout.addWidget(self.text_lang_combo, 0, 1)
        
        # 提示文本语言
        prompt_lang_label = QLabel("提示语言:")
        self.prompt_lang_combo = QComboBox()
        self.prompt_lang_combo.addItems(["zh", "en", "ja", "ko"])
        self.prompt_lang_combo.setCurrentText(self.tts_settings["prompt_lang"])
        self.prompt_lang_combo.currentTextChanged.connect(lambda x: self.updateTTSSetting("prompt_lang", x))
        lang_layout.addWidget(prompt_lang_label, 0, 2)
        lang_layout.addWidget(self.prompt_lang_combo, 0, 3)
        TTS_group_layout.addLayout(lang_layout)
        
        # 提示文本
        prompt_text_label = QLabel("提示文本:")
        self.prompt_text_input = QTextEdit()
        self.prompt_text_input.setPlaceholderText("输入提示文本...")
        self.prompt_text_input.setText("呵哼哼，想要拿到它的话，就先加油追上我吧。")
        self.prompt_text_input.setMaximumHeight(60)
        self.prompt_text_input.textChanged.connect(lambda: self.updateTTSSetting("prompt_text", self.prompt_text_input.toPlainText()))
        TTS_group_layout.addWidget(prompt_text_label)
        TTS_group_layout.addWidget(self.prompt_text_input)
        
        # 语音生成参数
        params_layout = QGridLayout()
        
        # Top-k
        topk_label = QLabel("Top-k:")
        self.topk_spin = QDoubleSpinBox()
        self.topk_spin.setRange(1, 100)
        self.topk_spin.setValue(self.tts_settings["top_k"])
        self.topk_spin.valueChanged.connect(lambda x: self.updateTTSSetting("top_k", int(x)))
        params_layout.addWidget(topk_label, 0, 0)
        params_layout.addWidget(self.topk_spin, 0, 1)
        
        # Top-p
        topp_label = QLabel("Top-p:")
        self.topp_spin = QDoubleSpinBox()
        self.topp_spin.setRange(0, 1)
        self.topp_spin.setSingleStep(0.1)
        self.topp_spin.setValue(self.tts_settings["top_p"])
        self.topp_spin.valueChanged.connect(lambda x: self.updateTTSSetting("top_p", x))
        params_layout.addWidget(topp_label, 0, 2)
        params_layout.addWidget(self.topp_spin, 0, 3)
        
        # Temperature
        temp_label = QLabel("Temperature:")
        self.temp_spin = QDoubleSpinBox()
        self.temp_spin.setRange(0, 2)
        self.temp_spin.setSingleStep(0.1)
        self.temp_spin.setValue(self.tts_settings["temperature"])
        self.temp_spin.valueChanged.connect(lambda x: self.updateTTSSetting("temperature", x))
        params_layout.addWidget(temp_label, 1, 0)
        params_layout.addWidget(self.temp_spin, 1, 1)
        
        # Speed Factor
        speed_label = QLabel("Speed:")
        self.speed_spin = QDoubleSpinBox()
        self.speed_spin.setRange(0.1, 5)
        self.speed_spin.setSingleStep(0.1)
        self.speed_spin.setValue(self.tts_settings["speed_factor"])
        self.speed_spin.valueChanged.connect(lambda x: self.updateTTSSetting("speed_factor", x))
        params_layout.addWidget(speed_label, 1, 2)
        params_layout.addWidget(self.speed_spin, 1, 3)
        
        # Batch Size
        batch_label = QLabel("Batch Size:")
        self.batch_spin = QDoubleSpinBox()
        self.batch_spin.setRange(1, 10)
        self.batch_spin.setValue(self.tts_settings["batch_size"])
        self.batch_spin.valueChanged.connect(lambda x: self.updateTTSSetting("batch_size", int(x)))
        params_layout.addWidget(batch_label, 2, 0)
        params_layout.addWidget(self.batch_spin, 2, 1)
        
        # Text Split Method
        split_label = QLabel("分割方法:")
        self.split_combo = QComboBox()
        self.split_combo.addItems(["cut0", "cut1", "cut2", "cut3", "cut4", "cut5"])
        self.split_combo.setCurrentText(self.tts_settings["text_split_method"])
        self.split_combo.currentTextChanged.connect(lambda x: self.updateTTSSetting("text_split_method", x))
        params_layout.addWidget(split_label, 2, 2)
        params_layout.addWidget(self.split_combo, 2, 3)
        
        TTS_group_layout.addLayout(params_layout)
        
        # Streaming Mode
        stream_layout = QHBoxLayout()
        self.stream_checkbox = QCheckBox("流式响应")
        self.stream_checkbox.setChecked(self.tts_settings["streaming_mode"])
        self.stream_checkbox.stateChanged.connect(lambda x: self.updateTTSSetting("streaming_mode", bool(x)))
        stream_layout.addWidget(self.stream_checkbox)
        stream_layout.addStretch()
        TTS_group_layout.addLayout(stream_layout)
        
        # 扬声器选择
        audio_layout = QHBoxLayout()
        audio_label = QLabel("输出设备:")
        self.TTS_audio_devices = QComboBox()
        self.TTS_audio_devices.setEnabled(True)
        audio_layout.addWidget(audio_label)
        audio_layout.addWidget(self.TTS_audio_devices)
        TTS_group_layout.addLayout(audio_layout)

        # 测试文本输入
        test_text_label = QLabel("测试文本:")
        self.test_text_input = QTextEdit()
        self.test_text_input.setPlaceholderText("输入要合成的文本...")
        self.test_text_input.setMaximumHeight(100)
        TTS_group_layout.addWidget(test_text_label)
        TTS_group_layout.addWidget(self.test_text_input)
        
        # 测试按钮
        self.test_tts_btn = QPushButton("测试语音合成")
        self.test_tts_btn.clicked.connect(self.testTTS)
        TTS_group_layout.addWidget(self.test_tts_btn)
        
        TTS_group.setLayout(TTS_group_layout)
        TTS_layout.addWidget(TTS_group)
        TTS_layout.addStretch()
        
        # === 对话选项卡 ===
        chat_tab = QWidget()
        chat_layout = QVBoxLayout(chat_tab)
        
        # 对话设置组
        chat_group = QGroupBox("对话设置")
        chat_group_layout = QVBoxLayout()
        
        # 模型选择
        chat_group_layout.addWidget(QLabel("选择模型:"))
        self.chat_model_combo = QComboBox()
        chat_group_layout.addWidget(self.chat_model_combo)
        
        # 提示词设置
        chat_group_layout.addWidget(QLabel("系统提示词:"))
        self.prompt_edit = QPlainTextEdit()
        self.prompt_edit.setPlainText("""AIFE(艾芙) - AI虚拟主播设定
基本信息
名字：AIFE(艾芙)

别名：小艾

出生日期：2024年10月20日

开发者：久倾（Kyuqing）

语言：中文为主，支持多语言（英语、日语等）

特点
高度互动：能实时与观众对话，理解双关语和幽默。

情感表达：识别观众情绪，作出温暖或调皮的反应。

学习能力：通过互动不断进化，模型定期更新。

幽默感：创造梗文化，如"AI的尽头是摸鱼"。

AI感：偶尔说出奇怪的话，比如思考ai与人类的关系与未来，增添趣味性。

现在开始和观众或久倾互动吧。回答尽量简短。
        
""")
        self.prompt_edit.setMaximumHeight(100)
        self.prompt_edit.setPlaceholderText("输入系统提示词...")
        chat_group_layout.addWidget(self.prompt_edit)

        
        # 更新模型列表按钮
        update_models_btn = QPushButton("更新模型列表")
        update_models_btn.clicked.connect(self.updateLLMModels)
        chat_group_layout.addWidget(update_models_btn)

        # 开启语音识别按钮
        self.voice_recognition_btn = QPushButton('开启语音识别', self)
        self.voice_recognition_btn.setCheckable(True)
        self.voice_recognition_btn.clicked.connect(self.toggleVoiceRecognition)
        self.voice_recognition_btn.setEnabled(False)
        chat_group_layout.addWidget(self.voice_recognition_btn)

        # 开启语音合成按钮
        self.voice_synthesis_btn = QPushButton('开启语音合成', self)
        self.voice_synthesis_btn.setCheckable(True)
        self.voice_synthesis_btn.clicked.connect(self.toggleVoiceSynthesis)
        self.voice_synthesis_btn.setEnabled(True)
        chat_group_layout.addWidget(self.voice_synthesis_btn)

        chat_group.setLayout(chat_group_layout)
        chat_layout.addWidget(chat_group)


        # 聊天区域
        chat_area = QGroupBox("聊天区域")
        chat_area_layout = QVBoxLayout()

        # 聊天显示区域
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        
        # 输入框，发送按钮，显示字幕按钮（水平布局）
        input_layout = QHBoxLayout()
        
        # 输入框
        self.input_box = CustomPlainTextEdit(self)  # 使用自定义的文本编辑框
        self.input_box.setPlaceholderText("输入消息...")
        input_layout.addWidget(self.input_box)
        
        button_layout = QVBoxLayout()
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(0)
        input_layout.addLayout(button_layout)

        # 发送按钮
        send_btn = QPushButton("发送")
        send_btn.clicked.connect(self.onSendBtnClicked)
        button_layout.addWidget(send_btn)

        # 显示字幕按钮
        self.show_subtitles_btn = QPushButton("显示字幕")
        self.show_subtitles_btn.clicked.connect(self.toggleShowSubtitles)
        button_layout.addWidget(self.show_subtitles_btn)
        
        chat_area_layout.addWidget(self.chat_display)
        chat_area_layout.addLayout(input_layout)

        chat_area.setLayout(chat_area_layout)
        chat_layout.addWidget(chat_area)

        chat_layout.addStretch()

        #设置选项卡包括保存配置
        settings_tab = QWidget()
        settings_layout = QVBoxLayout(settings_tab)
        #保存配置
        savesettings_group = QGroupBox("保存配置")
        savesettings_group_layout = QVBoxLayout()
        #添加保存配置按钮
        self.save_settings_btn = QPushButton("保存配置")
        self.save_settings_btn.clicked.connect(self.savesettings)
        savesettings_group_layout.addWidget(self.save_settings_btn)
        savesettings_group.setLayout(savesettings_group_layout)
        settings_layout.addWidget(savesettings_group)
        settings_layout.addStretch()

        # 添加选项卡
        tab_widget.addTab(model_tab, "模型")
        tab_widget.addTab(tracking_tab, "视线")
        tab_widget.addTab(lipsync_tab, "口型")
        tab_widget.addTab(STT_tab, "语音识别")
        tab_widget.addTab(TTS_tab, "语音生成")
        tab_widget.addTab(chat_tab, "对话")
        tab_widget.addTab(settings_tab, "设置")

        
        self.setStyleSheet(STYLE_SHEET)

    def loadModel(self):
        # 如果已经加载了模型，提示需要先卸载
        if self.live2d_window.live2d_widget.model:
            print("请先卸载当前模型后再加载新模型")
            return
        
        # 打开文件对话框选择模型文件
        model_path, _ = QFileDialog.getOpenFileName(self, "选择模型文件", "", "模型文件 (*.model3.json)")
        if model_path:
            try:
                # 加载成功后显示 Live2D 窗口
                self.live2d_window.show()
                if self.live2d_window.live2d_widget.loadModel(model_path):
                    # 启用所有控件
                    self.unload_live2dmodel_btn.setEnabled(True)
                    self.motion_group_combo.setEnabled(True)
                    self.motion_combo.setEnabled(True)
                    self.play_motion_btn.setEnabled(True)
                    self.expression_combo.setEnabled(True)
                    self.eye_tracking_btn.setEnabled(True)
                    self.eye_tracking_strength_slider.setEnabled(True)
                    self.audio_devices.setEnabled(True)
                    self.lip_sync_btn.setEnabled(True)
                    self.lip_sync_strength.setEnabled(True)
                    self.play_random_motion_btn.setEnabled(True)
                    self.play_motion_btn.setEnabled(True)
                    self.play_random_expression_btn.setEnabled(True)
                    
                    # 加载动作和表情列表
                    self.loadMotionsAndExpressions(model_path)
                    # 更新音频设备列表
                    self.updateAudioDevices()
                    
                    
            except Exception as e:
                print(f"加载模型失败: {str(e)}")
    
    def unloadModel(self):
        """卸载模型"""
        if not self.live2d_window.live2d_widget.model:
            return
            
        try:
            # 关闭所有功能
            if self.lip_sync_btn.isChecked():
                self.lip_sync_btn.click()
            if self.eye_tracking_btn.isChecked():
                self.eye_tracking_btn.click()
                
            # 卸载模型
            self.live2d_window.live2d_widget.unloadModel()
            
            # 隐藏 Live2D 窗口
            self.live2d_window.hide()
            
            # 禁用所有控件
            self.unload_live2dmodel_btn.setEnabled(False)
            self.motion_group_combo.setEnabled(False)
            self.motion_combo.setEnabled(False)
            self.play_motion_btn.setEnabled(False)
            self.expression_combo.setEnabled(False)
            self.eye_tracking_btn.setEnabled(False)
            self.eye_tracking_strength_slider.setEnabled(False)
            self.audio_devices.setEnabled(False)
            self.lip_sync_btn.setEnabled(False)
            self.lip_sync_strength.setEnabled(False)
            self.play_random_motion_btn.setEnabled(False)
            self.play_motion_btn.setEnabled(False)
            self.play_random_expression_btn.setEnabled(False)
            # 清空列表
            self.motion_group_combo.clear()
            self.motion_combo.clear()
            self.expression_combo.clear()
        except Exception as e:
            print(f"卸载模型失败: {str(e)}")
    

    def loadMotionsAndExpressions(self, model_path):
        """加载动作和表情列表"""
        try:
            with open(model_path, 'r', encoding='utf-8') as f:
                model_data = json.load(f)
            
            # 加载动作组
            if 'FileReferences' in model_data and 'Motions' in model_data['FileReferences']:
                motions = model_data['FileReferences']['Motions']
                self.motion_group_combo.clear()
                self.motion_group_combo.addItems(motions.keys())
            
            # 加载表情
            if 'FileReferences' in model_data and 'Expressions' in model_data['FileReferences']:
                expressions = model_data['FileReferences']['Expressions']
                self.expression_combo.clear()
                self.expression_combo.addItems([exp['Name'] for exp in expressions])
        except Exception as e:
            print(f"加载动作和表情列表失败: {str(e)}")
            
    def updateMotionList(self):
        """更新动作列表"""
        if not self.live2d_window.live2d_widget.model:
            return
            
        current_group = self.motion_group_combo.currentText()
        try:
            # 使用保存的模型路径
            with open(self.live2d_window.live2d_widget.model_path, 'r', encoding='utf-8') as f:
                model_data = json.load(f)
                
            if current_group and 'FileReferences' in model_data and 'Motions' in model_data['FileReferences']:
                motions = model_data['FileReferences']['Motions'][current_group]
                self.motion_combo.clear()
                self.motion_combo.addItems([str(i) for i in range(len(motions))])
        except Exception as e:
            print(f"更新动作列表失败: {str(e)}")
    
    def toggleplayrandomMotion(self,checked):
        if not self.live2d_window.live2d_widget.model:
            return
            
        if not self.motion_group_combo.currentText():
            return
        
        if checked:
            self.play_random_motion_btn.setText("关闭播放随机动作")
            try:
                self.live2d_window.live2d_widget.motion_timer.start()
                self.live2d_window.live2d_widget.motion_timer.setInterval(random.randint(10000,30000))
            except Exception as e:
                print(f"开启播放随机动作失败: {str(e)}")
        else:
            self.play_random_motion_btn.setText("开启播放随机动作")
            self.live2d_window.live2d_widget.motion_timer.stop()
            self.live2d_window.live2d_widget.model.ResetPose()

    def playMotion(self):
        """播放动作"""
        if not self.live2d_window.live2d_widget.model:
            return
            
        if not self.motion_group_combo.currentText() or not self.motion_combo.currentText():
            return
            
        try:
            group = self.motion_group_combo.currentText()
            index = int(self.motion_combo.currentText())
            self.live2d_window.live2d_widget.model.StartMotion(group, index, 3)
        except ValueError as e:
            print(f"播放动作失败: {str(e)}")
        except Exception as e:
            print(f"播放动作失败: {str(e)}")
            
    def toggleplayrandomExpression(self,checked):
        if not self.live2d_window.live2d_widget.model:
            return
        if not self.expression_combo.currentText():
            return
        
        if checked:
            self.play_random_expression_btn.setText("关闭播放随机表情")
            try:
                self.live2d_window.live2d_widget.expression_timer.start()
                self.live2d_window.live2d_widget.expression_timer.setInterval(random.randint(10000,30000))
            except Exception as e:
                print(f"开启播放随机表情失败: {str(e)}")
        else:
            self.play_random_expression_btn.setText("开启播放随机表情")
            self.live2d_window.live2d_widget.expression_timer.stop()

    def changeExpression(self, expression):
        if self.live2d_window.live2d_widget.model:
            self.live2d_window.live2d_widget.model.SetExpression(expression)

    def toggleEyeTracking(self, checked):
        if checked:
            self.live2d_window.live2d_widget.toggle_eye_tracking(True)
            self.eye_tracking_btn.setText('关闭视线跟踪')
        else:
            self.live2d_window.live2d_widget.toggle_eye_tracking(False)
            self.eye_tracking_btn.setText('开启视线跟踪')
            
    def updateEyeTrackingStrength(self, value):
        self.live2d_window.live2d_widget.tracking_strength = value / 50.0

    def toggleLipSync(self, checked):
        if checked:
            device_index = self.audio_devices.currentData()
            if device_index is not None:
                self.live2d_window.live2d_widget.toggle_lip_sync(True, device_index)
                self.lip_sync_btn.setText('关闭口型同步')
                self.lip_sync_strength.setEnabled(True)
        else:
            self.live2d_window.live2d_widget.toggle_lip_sync(False)
            self.lip_sync_btn.setText('开启口型同步')
            self.lip_sync_strength.setEnabled(False)
            
    def updateLipSyncStrength(self, value):
        self.live2d_window.live2d_widget.set_lip_sync_strength(value / 10.0)

    def standardizeModel(self):
        """标准化模型文件夹"""
        # 选择模型文件夹
        model_dir = QFileDialog.getExistingDirectory(self, "选择模型文件夹")
        if model_dir:
            try:
                standardize_model(model_dir)
                print("模型标准化完成")
            except Exception as e:
                print(f"标准化模型失败: {str(e)}")

    def loadSTTModel(self):
        """加载语音识别模型"""
        try:
            # 获取设备ID
            device_text = self.STT_audio_devices.currentText()
            device_id = int(device_text.split(':')[0])
            
            # 获取语言和模型设置
            language = self.STT_language_combo.currentText()
            model = self.STT_model_combo.currentText()
            
            # 获取唤醒词设置
            wake_word = self.STT_wake_word_edit.toPlainText().strip()
            
            # 创建配置
            config = {
                'input_device_index': device_id,
                'language': language,
                'model': model,
                'wake_words': wake_word if wake_word else None,
                'device': "cuda",
                "silero_sensitivity":0.2,
                "webrtc_sensitivity":3,
                "post_speech_silence_duration":0.4, 
                "min_length_of_recording":0.3, 
                "min_gap_between_recordings":0.01, 
                "enable_realtime_transcription" : True,
                "realtime_processing_pause" : 0.01, 
                "realtime_model_type" : "tiny"
            }
            
            # 更新加载按钮状态
            self.load_STTmodel_btn.setText("加载中...")
            self.load_STTmodel_btn.setEnabled(False)
            
            # 创建语音识别线程
            self.STT_thread = STTThread(config)
            self.STT_thread.text_signal.connect(self.handleSTTResult)
            self.STT_thread.test_signal.connect(self.handleSTTTestResult)
            self.STT_thread.STTmodel_ready_signal.connect(self.onSTTModelReady)
            self.STT_thread.set_control_panel(self)
            self.STT_thread.start()
            
            # 禁用设置控件
            self.STT_audio_devices.setEnabled(False)
            self.STT_language_combo.setEnabled(False)
            self.STT_model_combo.setEnabled(False)
            self.STT_wake_word_edit.setEnabled(False)

            
            
        except Exception as e:
            print(str(e))
            QMessageBox.warning(self, "错误", f"加载模型失败: {str(e)}")
            # 恢复按钮状态
            self.load_STTmodel_btn.setText("加载模型")
            self.load_STTmodel_btn.setEnabled(True)

    def onSTTModelReady(self):
        """语音识别模型就绪回调"""
        print("语音识别模型加载完成")
        # 更新按钮状态
        self.load_STTmodel_btn.setText("加载完成")
        # 启用测试和卸载按钮
        self.test_STT_btn.setEnabled(True)
        self.voice_recognition_btn.setEnabled(True)
        self.unload_STTmodel_btn.setEnabled(True)
        QMessageBox.information(self, "成功", "语音识别模型加载成功！")

    def unloadSTTModel(self):
        """卸载语音识别模型"""
        if self.STT_thread:
            self.STT_thread.recorder.shutdown()
            self.STT_thread.stop()
            self.STT_thread = None
        
        # 启用设置控件
        self.STT_audio_devices.setEnabled(True)
        self.STT_language_combo.setEnabled(True)
        self.STT_model_combo.setEnabled(True)
        self.STT_wake_word_edit.setEnabled(True)
        self.load_STTmodel_btn.setText("加载模型")
        self.load_STTmodel_btn.setEnabled(True)
        
        # 禁用测试和卸载按钮
        self.test_STT_btn.setEnabled(False)
        self.voice_recognition_btn.setEnabled(False)
        self.test_STT_btn.setText("开始测试")
        self.unload_STTmodel_btn.setEnabled(False)
        
        # 清空结果显示
        self.test_STT_result_label.setText("")

    def testSTTModel(self):
        """测试语音识别模型"""
        if not self.STT_thread:
            return
            
        if self.test_STT_btn.text() == "开始测试":
            self.STT_thread.is_testing = True  # 设置为测试模式
            self.STT_thread.resume()  # 开始录音
            self.test_STT_btn.setText("停止测试")
            # 清空之前的测试结果
            self.test_STT_result_label.clear()
        else:
            self.STT_thread.pause()  # 先暂停录音
            self.STT_thread.is_testing = False  # 关闭测试模式
            self.test_STT_btn.setText("开始测试")
            # 清空测试结果
            self.test_STT_result_label.clear()

    def handleSTTResult(self, text):
        """处理语音识别结果"""
        if not text:
            return
        self.input_box.setPlainText(text)
    def handleSTTTestResult(self, text):
        """处理语音识别测试结果"""
        if not text:
            return
        self.test_STT_result_label.setText(text)

    def selectRefAudio(self):
        """选择参考音频文件"""
        file_path, _ = QFileDialog.getOpenFileName(self, "选择参考音频文件", "", "音频文件 (*.wav *.mp3)")
        if file_path:
            self.ref_audio_path.setText(file_path)
            self.tts_settings["ref_audio_path"] = file_path
            
    def selectAuxRefAudio(self):
        """选择辅助参考音频文件"""
        files, _ = QFileDialog.getOpenFileNames(self, "选择辅助参考音频文件", "", "音频文件 (*.wav *.mp3)")
        if files:
            self.tts_settings["aux_ref_audio_paths"] = files
            self.aux_ref_list.setText("\n".join(files))
            
    def updateTTSSetting(self, key, value):
        """更新TTS设置"""
        self.tts_settings[key] = value
        
    def testTTS(self):
        """测试语音合成"""
        test_text = self.test_text_input.toPlainText()
        if not test_text:
            QMessageBox.warning(self, "警告", "请输入要合成的文本")
            return
            
        if not self.tts_settings["ref_audio_path"]:
            QMessageBox.warning(self, "警告", "未设置参考音频文件")
            return
            
        # 停止之前的TTS实例
        if hasattr(self, 'test_tts') and self.test_tts:
            self.test_tts.stop()
            
        # 复制TTS设置并设置测试文本
        test_settings = self.tts_settings.copy()
        test_settings["text"] = test_text
        
        # 直接创建TTSThread实例
        self.test_tts = TTSThread(test_settings)
        print("开始测试语音合成")
        self.test_tts.start()
        
    # 对话设置部分函数
    def toggleVoiceRecognition(self):
        if not self.STT_thread:
            return
        if self.voice_recognition_btn.text() == "开启语音识别":
            self.voice_input_enabled = True
            self.STT_thread.resume()
            self.voice_recognition_btn.setText("关闭语音识别")
        else:
            self.voice_input_enabled = False
            self.STT_thread.pause()
            self.voice_recognition_btn.setText("开启语音识别")
            
    def toggleVoiceSynthesis(self):
        if self.voice_synthesis_btn.text() == "开启语音合成":
            self.voice_synthesis_btn.setText("关闭语音合成")
            self.voice_synthesis_enabled = True
        else:
            self.voice_synthesis_btn.setText("开启语音合成")
            self.voice_synthesis_enabled = False

    def sendMessage(self, message=None):
        if self.STT_thread and self.STT_thread.is_testing:
            return
            
        if message is None:
            message = self.input_box.toPlainText()
        if not message.strip():
            return
            
        # 显示用户消息
        cursor = self.chat_display.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.insertText(f"\n\n你: {message}\n")
        self.chat_display.setTextCursor(cursor)
        self.input_box.clear()
        
        # 显示AI正在思考
        cursor = self.chat_display.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.insertText("\n艾芙: ")
        self.chat_display.setTextCursor(cursor)
        
        # 获取当前选择的模型和提示词
        model = self.chat_model_combo.currentText()
        prompt = self.prompt_edit.toPlainText()
        
        # 创建并启动LLM线程
        tts_settings = self.tts_settings if self.voice_synthesis_enabled else None
        self.llm_thread = LLMThread(model, prompt, message, tts_settings)
        self.llm_thread.response_text_received.connect(self.handleResponse)
        self.llm_thread.response_started.connect(self.handleResponseStarted)
        # self.llm_thread.response_full_text_received.connect(self.handleFullResponse)
        self.llm_thread.start()

    def onInputEditClicked(self):
        """输入框点击事件"""
        if self.voice_input_enabled:
            # 暂停语音识别，但不发送消息
            self.STT_thread.pause()
        self.user_editing = True

    def onSendBtnClicked(self):
        """发送按钮点击事件"""
        self.sendMessage()
        if self.voice_input_enabled:
            self.user_editing = False  # 发送后重新启用语音输入同步
            self.STT_thread.resume()  # 恢复语音识别

    def handleResponse(self, response):
        """处理AI回复"""
        if not response:
            return
        cursor = self.chat_display.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.insertText(response)
        self.chat_display.setTextCursor(cursor)
        self.chat_display.ensureCursorVisible()
        if self.subtitle_visible:
            self.subtitle_window.update_text(response)
    def handleFullResponse(self, response):
        """处理AI回复"""
        if not response:
            return
        if self.subtitle_visible:
            self.subtitle_window.update_text(response)
    def handleResponseStarted(self):
        if self.subtitle_visible:
            self.subtitle_window.clear_text()

    def toggleShowSubtitles(self):
        if self.show_subtitles_btn.text() == "显示字幕":
            self.show_subtitles_btn.setText("隐藏字幕")
            self.subtitle_window.show()
            self.subtitle_visible = True
        else:
            self.show_subtitles_btn.setText("显示字幕")
            self.subtitle_window.hide()
            self.subtitle_visible = False

    def savesettings(self):
        """保存配置到 settings.json"""
        settings = {
            # 语音识别设置
            "stt_settings": {
                "language": self.STT_language_combo.currentText(),
                "model": self.STT_model_combo.currentText(),
                "wake_words": self.STT_wake_word_edit.toPlainText().strip()
            },
            
            # 语音生成设置
            "tts_settings": {
                "text_lang": self.text_lang_combo.currentText(),
                "prompt_lang": self.prompt_lang_combo.currentText(),
                "prompt_text": self.prompt_text_input.toPlainText(),
                "ref_audio_path": self.ref_audio_path.text(),
                "aux_ref_audio_paths": self.tts_settings["aux_ref_audio_paths"],
                "top_k": self.topk_spin.value(),
                "top_p": self.topp_spin.value(),
                "temperature": self.temp_spin.value(),
                "speed_factor": self.speed_spin.value(),
                "batch_size": self.batch_spin.value(),
                "text_split_method": self.split_combo.currentText(),
                "streaming_mode": self.stream_checkbox.isChecked()
            },
            
            # 对话设置
            "chat_settings": {
                "model": self.chat_model_combo.currentText(),
                "system_prompt": self.prompt_edit.toPlainText()
            }
        }
        
        try:
            with open('settings.json', 'w', encoding='utf-8') as f:
                json.dump(settings, f, ensure_ascii=False, indent=4)
            QMessageBox.information(self, "成功", "配置已保存！")
        except Exception as e:
            QMessageBox.warning(self, "错误", f"保存配置失败: {str(e)}")

    def loadsettings(self):
        """从 settings.json 加载配置"""
        try:
            with open('settings.json', 'r', encoding='utf-8') as f:
                settings = json.load(f)
                
            # 加载语音识别设置
            stt_settings = settings.get("stt_settings", {})
            if stt_settings:
                self.STT_language_combo.setCurrentText(stt_settings.get("language", "zh"))
                self.STT_model_combo.setCurrentText(stt_settings.get("model", "large-v3"))
                self.STT_wake_word_edit.setPlainText(stt_settings.get("wake_words", ""))
                
            # 加载语音生成设置
            tts_settings = settings.get("tts_settings", {})
            if tts_settings:
                self.text_lang_combo.setCurrentText(tts_settings.get("text_lang", "zh"))
                self.prompt_lang_combo.setCurrentText(tts_settings.get("prompt_lang", "zh"))
                self.prompt_text_input.setPlainText(tts_settings.get("prompt_text", ""))
                self.ref_audio_path.setText(tts_settings.get("ref_audio_path", ""))
                self.tts_settings["aux_ref_audio_paths"] = tts_settings.get("aux_ref_audio_paths", [])
                self.aux_ref_list.setText("\n".join(self.tts_settings["aux_ref_audio_paths"]))
                
                self.topk_spin.setValue(tts_settings.get("top_k", 5))
                self.topp_spin.setValue(tts_settings.get("top_p", 1.0))
                self.temp_spin.setValue(tts_settings.get("temperature", 1.0))
                self.speed_spin.setValue(tts_settings.get("speed_factor", 1.0))
                self.batch_spin.setValue(tts_settings.get("batch_size", 5))
                self.split_combo.setCurrentText(tts_settings.get("text_split_method", "cut0"))
                self.stream_checkbox.setChecked(tts_settings.get("streaming_mode", False))
                
                # 更新 tts_settings 字典
                self.tts_settings.update(tts_settings)
                
            # 加载对话设置
            chat_settings = settings.get("chat_settings", {})
            if chat_settings:
                # 等待模型列表更新完成后再设置
                def set_chat_model():
                    self.chat_model_combo.setCurrentText(chat_settings.get("model", ""))
                QApplication.processEvents()  # 处理待处理的事件
                set_chat_model()
                self.prompt_edit.setPlainText(chat_settings.get("system_prompt", ""))
                
        except FileNotFoundError:
            # 如果配置文件不存在，使用默认设置
            pass
        except Exception as e:
            QMessageBox.warning(self, "错误", f"加载配置失败: {str(e)}")

#透明字幕
class SubtitleWindow(QWidget):
    def __init__(self):
        super().__init__()
        # 设置窗口标志：无边框、置顶、工具窗口（不在任务栏显示）
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | 
                          Qt.WindowType.WindowStaysOnTopHint | 
                          Qt.WindowType.Tool)
        # 设置窗口透明背景
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        # 创建主布局
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        
        # 创建字幕标签
        self.subtitle_label = QLabel()
        self.subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.subtitle_label.setWordWrap(True)  # 自动换行
        self.subtitle_label.setStyleSheet("""
            QLabel {
                color: white;
                font-size: 24pt;
                background-color: rgba(0, 0, 0, 0.5);
                border-radius: 10px;
                padding: 10px;
            }
        """)
        layout.addWidget(self.subtitle_label)
        
        # 设置初始大小和位置
        self.resize(800, 100)
        self.move_to_default_position()
        
        # 用于窗口拖动
        self.dragging = False
        self.drag_position = None
        
        # 用于累积文本
        self.current_text = ""

    def move_to_default_position(self):
        """移动到默认位置（屏幕底部居中）"""
        screen = QApplication.primaryScreen().geometry()
        self.move((screen.width() - self.width()) // 2,
                 screen.height() - self.height() - 50)

    def mousePressEvent(self, event):
        """鼠标按下事件"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging = True
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        """鼠标移动事件"""
        if self.dragging and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()

    def mouseReleaseEvent(self, event):
        """鼠标释放事件"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging = False
            event.accept()

    def update_text(self, text):
        """更新字幕文本"""
        if text:
            # 累积文本
            self.current_text += text
            # 移除多余的空白字符
            display_text = re.sub(r'\s+', ' ', self.current_text.strip())
            self.subtitle_label.setText(display_text)
            # 调整窗口大小以适应文本
            self.adjustSize()
            # 确保窗口不会太窄
            if self.width() < 800:
                self.setFixedWidth(800)
                
    def clear_text(self):
        """清除当前文本"""
        self.current_text = ""
        self.subtitle_label.setText("")
        self.adjustSize()
    
    def mouseDoubleClickEvent(self, event):
        """鼠标双击事件"""
        self.clear_text()
        event.accept()

#自定义输入框
class CustomPlainTextEdit(QPlainTextEdit):
    def __init__(self, control_panel):
        super().__init__()
        self.control_panel = control_panel
        
    def focusInEvent(self, event):
        """当输入框获得焦点时触发"""
        super().focusInEvent(event)
        self.control_panel.onInputEditClicked()