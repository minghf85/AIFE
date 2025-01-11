import sys
import os
from RealtimeSTT import AudioToTextRecorder
import requests
import json
from typing import Optional
import wave
import io
from PyQt6.QtWidgets import (QApplication, QMainWindow, QPushButton, QVBoxLayout, 
                           QHBoxLayout, QWidget, QFileDialog, QLabel, QComboBox,
                           QGroupBox, QScrollArea, QFrame, QMessageBox, QSlider, QTabWidget,
                           QTextEdit, QMenu, QPlainTextEdit, QLineEdit, QDoubleSpinBox, QGridLayout,QCheckBox)
from PyQt6.QtCore import Qt, QTimer, QPoint, pyqtSignal, QThread, QRect, QPropertyAnimation, QTime
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from PyQt6.QtGui import QSurfaceFormat, QPalette, QColor, QFont, QCursor
from OpenGL.GL import *
import live2d.v3 as live2d
from standardize import standardize_model
from mic_lipsync import MicLipSync
from TTS import TTSThread
from openai import OpenAI
import math
import pyaudio as pa
import ollama
import time
import threading


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

class TransparentOpenGLWidget(QOpenGLWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.model = None
        self.model_path = None  # 添加模型路径存储
        self.timer = QTimer()
        self.timer.timeout.connect(self.update)
        self.timer.start(1000 // 60)  # 60 FPS
        self.width = 300
        self.height = 600
        self.initialized = False
        
        # 口型同步相关
        self.lip_sync = MicLipSync()
        self.lip_sync_enabled = False
        self.lip_sync_strength = 3.0  # 口型同步强度
        
        # 视线跟踪相关
        self.eye_tracking_enabled = False
        self.tracking_strength = 1.0  # 整体跟随强度
        
        # 视线回正相关
        self.last_mouse_pos = QPoint()
        self.last_mouse_move_time = 0
        self.return_delay = 5000  # 3秒后回正
        self.is_returning = False
        self.current_angles = {"x": 0, "y": 0}  # 用于平滑过渡
        self.smooth_factor = 0.02  # 统一的平滑因子
        
        # 创建定时器用于更新视线位置
        self.eye_tracking_timer = QTimer()
        self.eye_tracking_timer.timeout.connect(self.updateEyeTracking)
        self.eye_tracking_timer.setInterval(16)  # 约60fps
        self.AllParams={}
        
    def initializeGL(self):
        # 初始化live2d
        live2d.init()
        # 初始化OpenGL
        live2d.glewInit()
        
        # 设置OpenGL
        glViewport(0, 0, self.width, self.height)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        glOrtho(0, self.width, self.height, 0, -1, 1)
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        
        self.initialized = True
    
    def resizeGL(self, w, h):
        self.width = w
        self.height = h
        glViewport(0, 0, w, h)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        glOrtho(0, w, h, 0, -1, 1)
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        
        if self.model:
            self.model.Resize(w, h)
    
    def paintGL(self):
        if not self.initialized:
            return
            
        try:
            # 使用OpenGL清空缓冲区
            glClearColor(0.0, 0.0, 0.0, 0.0)
            glClear(GL_COLOR_BUFFER_BIT)
            
            # 重置模型视图矩阵
            glMatrixMode(GL_MODELVIEW)
            glLoadIdentity()
            
            if self.model:
                # 更新模型基础状态（呼吸、动作、姿势等）
                self.model.Update()
                
                # 在Update之后，Draw之前应用参数更新
                
                # 1. 应用口型同步
                if self.lip_sync_enabled:
                    if self.lip_sync.update():  # 如果音频还在继续
                        self.model.SetParameterValue("ParamMouthOpenY", 
                            self.lip_sync.get_rms() * self.lip_sync_strength, 1.0)
                
                # 2. 应用视线跟踪
                if self.eye_tracking_enabled:
                    self.updateEyeTracking()
                
                # 执行绘制
                self.model.Draw()
        except Exception as e:
            print(f"绘制时出错: {str(e)}")
            self.cleanup()  # 出错时清理资源
            
    def cleanup(self):
        """清理资源"""
        try:
            if self.lip_sync_enabled:
                self.lip_sync.stop()
            if self.model:
                self.model = None
            if self.initialized:
                self.initialized = False
                live2d.dispose()
        except Exception as e:
            print(f"清理资源时出错: {str(e)}")
            
    def closeEvent(self, event):
        """关闭时清理资源"""
        if self.audio_stream:
            self.audio_stream.stop_stream()
            self.audio_stream.close()
            self.audio_stream = None
            
        if self.model:
            self.unloadModel()
            
        super().closeEvent(event)
        
    def __del__(self):
        """析构时确保资源被释放"""
        self.unloadModel()
        
    def unloadModel(self):
        """卸载模型并清理资源"""
        if self.model:
            try:
                self.model.Release()
                self.model = None
                self.model_path = None
                self.initialized = False
                self.AllParams.clear()
                print("模型已卸载")
            except Exception as e:
                print(f"卸载模型时出错: {str(e)}")
                
    def toggle_lip_sync(self, enabled: bool, device_index: Optional[int] = None):
        """切换口型同步状态"""
        if enabled and not self.lip_sync_enabled:
            if device_index is not None:
                self.lip_sync.select_device(device_index)
            self.lip_sync.start()
            self.lip_sync_enabled = True
        elif not enabled and self.lip_sync_enabled:
            self.lip_sync.stop()
            self.lip_sync_enabled = False
            
    def set_lip_sync_strength(self, value: float):
        """设置口型同步强度"""
        self.lip_sync_strength = value
        
    def toggle_eye_tracking(self, enabled: bool):
        """切换视线跟踪状态"""
        self.eye_tracking_enabled = enabled
        if enabled:
            # 开始跟踪时，不立即重置角度，让updateEyeTracking处理平滑过渡
            self.last_mouse_pos = QCursor.pos()
            self.last_mouse_move_time = QTime.currentTime().msecsSinceStartOfDay()
            self.eye_tracking_timer.start()
        else:
            # 关闭跟踪时，设置is_returning为True，让视线慢慢回正
            self.is_returning = True
            # 保持定时器运行，直到回正完成
            self.eye_tracking_timer.start()
            
    def updateEyeTracking(self):
        """更新视线跟踪"""
        if not self.model or not self.initialized or not self.window():
            return
            
        try:
            # 获取鼠标位置（屏幕坐标）
            cursor = QCursor.pos()
            current_time = QTime.currentTime().msecsSinceStartOfDay()
            
            # 如果启用了跟踪，检查鼠标移动
            if self.eye_tracking_enabled:
                # 检查鼠标是否移动（增加移动阈值，减少抖动）
                if (abs(cursor.x() - self.last_mouse_pos.x()) > 5 or 
                    abs(cursor.y() - self.last_mouse_pos.y()) > 5):
                    self.last_mouse_pos = cursor
                    self.last_mouse_move_time = current_time
                    self.is_returning = False
                
                # 检查是否应该开始回正
                time_since_last_move = current_time - self.last_mouse_move_time
                if not self.is_returning and time_since_last_move > self.return_delay:
                    self.is_returning = True
            
            # 获取目标位置
            if self.is_returning or not self.eye_tracking_enabled:
                # 回正或关闭跟踪时，目标是窗口中心
                cursor = self.window().frameGeometry().center()
            
            # 获取窗口的全局位置和大小
            window_geometry = self.window().frameGeometry()
            window_center = window_geometry.center()
            
            # 计算鼠标相对于窗口中心的偏移
            offset_x = cursor.x() - window_center.x()
            offset_y = cursor.y() - window_center.y()
            
            # 计算最大偏移距离（使用窗口宽高的一半）
            max_distance_x = window_geometry.width() / 2
            max_distance_y = window_geometry.height() / 2
            
            # 将偏移归一化到-1到1的范围
            target_x = max(-1, min(1, offset_x / max_distance_x)) * self.tracking_strength
            target_y = max(-1, min(1, offset_y / max_distance_y)) * self.tracking_strength
            
            # 平滑过渡到目标角度
            self.current_angles["x"] += (target_x - self.current_angles["x"]) * self.smooth_factor
            self.current_angles["y"] += (target_y - self.current_angles["y"]) * self.smooth_factor
            
            # 检查是否已经完全回正（用于关闭跟踪时）
            if not self.eye_tracking_enabled and abs(self.current_angles["x"]) < 0.01 and abs(self.current_angles["y"]) < 0.01:
                self.eye_tracking_timer.stop()
                self.current_angles["x"] = 0
                self.current_angles["y"] = 0
                
            def update_parameter(param_name, target_value, weight, scale=1.0, invert=False):
                if param_name not in self.AllParams or not self.model:
                    return
                    
                try:
                    value = target_value * scale * weight
                    if invert:
                        value = -value
                    
                    # 确保值在合理范围内
                    value = max(-90, min(90, value))
                    
                    self.model.SetParameterValue(param_name, float(value), 1.0)
                except Exception as e:
                    print(f"更新参数 {param_name} 时出错: {str(e)}")
            
            # 更新眼球参数
            update_parameter("ParamEyeBallX", self.current_angles["x"], 1.0)
            update_parameter("ParamEyeBallY", self.current_angles["y"], 1.0)
            
            # 更新头部参数
            head_weight = 2.5  # 头部跟随强度
            update_parameter("ParamAngleX", self.current_angles["x"], head_weight, 30)
            update_parameter("ParamAngleY", self.current_angles["y"], head_weight, 30, True)
            
            # 更新身体参数
            body_weight = 1.5  # 降低身体跟随强度
            update_parameter("ParamBodyAngleX", self.current_angles["x"], body_weight, 15)
            update_parameter("ParamBodyAngleY", self.current_angles["y"], body_weight, 15, True)
                
        except Exception as e:
            print(f"更新视线跟踪参数时出错: {str(e)}")
            self.cleanup()  # 出错时清理资源
            
    def loadModel(self, model_path):
        if not self.initialized:
            return
            
        try:
            if self.model:
                self.unloadModel()
                
            self.model = live2d.LAppModel()
            self.model.LoadModelJson(model_path)
            self.model.Resize(self.width, self.height)
            self.model_path = model_path  # 保存模型路径
            self.model.Update()
            self.scale = 1.0  # 重置缩放
            
            # 获取全部可用参数
            self.AllParams = {}
            for i in range(self.model.GetParameterCount()):
                param = self.model.GetParameter(i)
                param_id = param.id
                print(f"参数 {i}: {param_id}")  # 打印参数信息
                self.AllParams[param_id] = [i, param]  # 将参数id和参数对象保存在字典中
                
            return True
        except Exception as e:
            print(f"加载模型失败: {str(e)}")
            self.model = None
            self.model_path = None
            return False
            
    def unloadModel(self):
        """卸载当前模型"""
        if self.model:
            self.model = None
            self.update()
            return True
        return False

class ChatWindow(QWidget):
    def __init__(self, live2d_window, control_panel):
        super().__init__()
        self.live2d_window = live2d_window
        self.control_panel = control_panel
        self.setWindowFlags(
            Qt.WindowType.Tool | 
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        self.last_voice_text = ""
        self.voice_input_enabled = False
        self.voice_synthesis_enabled = False
        self.user_editing = False

        self.initUI()
        
    def initUI(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        self.setLayout(layout)
        
        # 聊天显示区域
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.chat_display.setStyleSheet("""
            QTextEdit {
                background-color: rgba(30, 30, 30, 180);
                color: white;
                border: 1px solid rgba(255, 255, 255, 100);
                border-radius: 10px;
                padding: 10px;
                font-size: 12px;
            }
            QScrollBar:vertical {
                background: rgba(0, 0, 0, 0);
                width: 10px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: rgba(255, 255, 255, 100);
                border-radius: 5px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)
        layout.addWidget(self.chat_display)
        
        # 输入区域
        input_layout = QHBoxLayout()
        input_layout.setSpacing(8)
        
        self.input_box = CustomPlainTextEdit(self)  # 使用自定义的文本编辑框
        self.input_box.setMaximumHeight(80)
        self.input_box.setStyleSheet("""
            QPlainTextEdit {
                background-color: rgba(40, 40, 40, 180);
                color: white;
                border: 1px solid rgba(255, 255, 255, 100);
                border-radius: 10px;
                padding: 8px;
                font-size: 12px;
            }
        """)
        input_layout.addWidget(self.input_box)
        
        button_layout = QVBoxLayout()
        button_layout.setSpacing(5)
        
        # 语音输入开启按钮
        self.voice_input_btn = QPushButton("语音输入")
        self.voice_input_btn.setFixedWidth(70)
        self.voice_input_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(60, 60, 60, 180);
                color: white;
                border: 1px solid rgba(255, 255, 255, 100);
                border-radius: 10px;
                padding: 8px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: rgba(80, 80, 80, 200);
                border: 1px solid rgba(255, 255, 255, 150);
            }
            QPushButton:pressed {
                background-color: rgba(40, 40, 40, 200);
            }
        """)
        self.voice_input_btn.clicked.connect(self.onVoiceInputBtnClicked)
        button_layout.addWidget(self.voice_input_btn)
        
        # 语音合成按钮
        self.voice_synthesis_btn = QPushButton("语音合成")
        self.voice_synthesis_btn.setFixedWidth(70)
        self.voice_synthesis_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(60, 60, 60, 180);
                color: white;
                border: 1px solid rgba(255, 255, 255, 100);
                border-radius: 10px;
                padding: 8px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: rgba(80, 80, 80, 200);
                border: 1px solid rgba(255, 255, 255, 150);
            }
            QPushButton:pressed {
                background-color: rgba(40, 40, 40, 200);
            }
        """)
        self.voice_synthesis_btn.clicked.connect(self.onVoiceSynthesisBtnClicked)
        button_layout.addWidget(self.voice_synthesis_btn)

        # 发送按钮
        self.send_btn = QPushButton("发送")
        self.send_btn.setFixedWidth(70)
        self.send_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(60, 60, 60, 180);
                color: white;
                border: 1px solid rgba(255, 255, 255, 100);
                border-radius: 10px;
                padding: 8px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: rgba(80, 80, 80, 200);
                border: 1px solid rgba(255, 255, 255, 150);
            }
            QPushButton:pressed {
                background-color: rgba(40, 40, 40, 200);
            }
        """)
        self.send_btn.clicked.connect(self.onSendBtnClicked)
        button_layout.addWidget(self.send_btn)
        
        input_layout.addLayout(button_layout)
        layout.addLayout(input_layout)
        
        self.setFixedSize(350, 500)
        
    def onVoiceInputBtnClicked(self):
        """语音输入按钮点击事件"""
        self.voice_input_enabled = not self.voice_input_enabled
        if self.voice_input_enabled:
            # 检查是否有语音识别线程
            if self.control_panel and self.control_panel.voice_thread:
                self.control_panel.voice_thread.resume()
            self.voice_input_btn.setStyleSheet("""
                QPushButton {
                    background-color: rgba(0, 255, 0, 150);
                    color: white;
                    border: 1px solid rgba(255, 255, 255, 100);
                    border-radius: 10px;
                    padding: 8px;
                    font-size: 12px;
                }
                QPushButton:hover {
                    background-color: rgba(0, 255, 0, 200);
                }
            """)
        else:
            # 暂停语音识别
            if self.control_panel and self.control_panel.voice_thread:
                self.control_panel.voice_thread.pause()
            self.voice_input_btn.setStyleSheet("""
                QPushButton {
                    background-color: rgba(60, 60, 60, 180);
                    color: white;
                    border: 1px solid rgba(255, 255, 255, 100);
                    border-radius: 10px;
                    padding: 8px;
                    font-size: 12px;
                }
                QPushButton:hover {
                    background-color: rgba(80, 80, 80, 200);
                    border: 1px solid rgba(255, 255, 255, 150);
                }
            """)
        self.voice_input_btn.update()

    def onInputEditClicked(self):
        """输入框点击事件"""
        if self.voice_input_enabled:
            # 暂停语音识别，但不发送消息
            self.control_panel.voice_thread.pause()
        self.user_editing = True

    def onSendBtnClicked(self):
        """发送按钮点击事件"""
        self.sendMessage()
        if self.voice_input_enabled:
            self.user_editing = False  # 发送后重新启用语音输入同步
            self.control_panel.voice_thread.resume()  # 恢复语音识别
        
    def sendMessage(self, message=None):
        if self.control_panel.voice_thread and self.control_panel.voice_thread.is_testing:
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
        cursor.insertText("\nAI: ")
        self.chat_display.setTextCursor(cursor)
        
        # 获取当前选择的模型和提示词
        model = self.control_panel.chat_model_combo.currentText()
        prompt = self.control_panel.prompt_edit.toPlainText()
        
        # 创建并启动Ollama线程
        tts_settings = self.control_panel.tts_settings if self.voice_synthesis_enabled else None
        self.ollama_thread = LLMThread(model, prompt, message, tts_settings)
        self.ollama_thread.response_text_received.connect(self.handleResponse)
        self.ollama_thread.response_full_text_received.connect(self.handleFullResponse)
        self.ollama_thread.start()

    def handleResponse(self, response):
        """处理AI回复"""
        if not response:
            return
        cursor = self.chat_display.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.insertText(response)
        self.chat_display.setTextCursor(cursor)
        self.chat_display.ensureCursorVisible()
    def handleFullResponse(self, response):
        """处理AI回复"""
        if not response:
            return
        cursor = self.chat_display.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.insertText(response)
        self.chat_display.setTextCursor(cursor)
        self.chat_display.ensureCursorVisible()
        

    def onVoiceSynthesisBtnClicked(self):
        """语音合成按钮点击事件"""
        self.voice_synthesis_enabled = not self.voice_synthesis_enabled
        if self.voice_synthesis_enabled:
            self.voice_synthesis_btn.setStyleSheet("""
                QPushButton {
                    background-color: rgba(0, 255, 0, 150);
                    color: white;
                    border: 1px solid rgba(255, 255, 255, 100);
                    border-radius: 10px;
                    padding: 8px;
                    font-size: 12px;
                }
                QPushButton:hover {
                    background-color: rgba(0, 255, 0, 200);
                }
            """)
        else:
            self.voice_synthesis_btn.setStyleSheet("""
                QPushButton {
                    background-color: rgba(60, 60, 60, 180);
                    color: white;
                    border: 1px solid rgba(255, 255, 255, 100);
                    border-radius: 10px;
                    padding: 8px;
                    font-size: 12px;
                }
                QPushButton:hover {
                    background-color: rgba(80, 80, 80, 200);
                    border: 1px solid rgba(255, 255, 255, 150);
                }
            """)
        self.voice_synthesis_btn.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragPosition = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            
    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.dragPosition)
            event.accept()

class CustomPlainTextEdit(QPlainTextEdit):
    def __init__(self, chat_window):
        super().__init__()
        self.chat_window = chat_window
        
    def focusInEvent(self, event):
        """当输入框获得焦点时触发"""
        super().focusInEvent(event)
        self.chat_window.onInputEditClicked()

from STT import STTThread

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
            
class Live2DWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        # 启用双缓冲
        self.setAttribute(Qt.WidgetAttribute.WA_PaintOnScreen, False)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        
        self.live2d_widget = TransparentOpenGLWidget()
        self.setCentralWidget(self.live2d_widget)
        
        self.setGeometry(100, 100, 300, 600)
        self.oldPos = self.pos()
        self.scale = 1.0
        self.base_width = 300
        self.base_height = 600
        
        # 添加缩放动画相关属性
        self.scale_animation = QPropertyAnimation(self, b"geometry")
        self.scale_animation.setDuration(100)  # 100ms的动画时长
        self.scale_animation.finished.connect(self.live2d_widget.update)
        
        # 创建聊天窗口
        self.chat_window = ChatWindow(self, None)  # 初始时control_panel为None，在main函数中设置
        
        # 移动相关
        self.is_moving = False
        
    def contextMenuEvent(self, event):
        menu = QMenu(self)
        
        # 根据聊天窗口状态显示不同的选项
        if self.chat_window.isVisible():
            chat_action = menu.addAction("关闭聊天")
        else:
            chat_action = menu.addAction("打开聊天")
            
        action = menu.exec(event.globalPos())
        
        if action == chat_action:
            if self.chat_window.isVisible():
                self.chat_window.hide()
            else:
                # 在模型右侧显示聊天窗口
                chat_pos = self.pos() + QPoint(self.width(), 0)
                self.chat_window.move(chat_pos)
                self.chat_window.show()

    def mousePressEvent(self, event):
        self.oldPos = event.globalPosition().toPoint()
        self.is_moving = True
        
    def mouseMoveEvent(self, event):
        if not self.is_moving:
            return
        delta = event.globalPosition().toPoint() - self.oldPos
        self.target_pos = self.pos() + QPoint(delta.x(), delta.y())
        self.oldPos = event.globalPosition().toPoint()
        
        # 直接移动到目标位置，不使用平滑效果
        self.move(self.target_pos)
        
    def mouseReleaseEvent(self, event):
        self.is_moving = False
        
    def wheelEvent(self, event):
        if not self.live2d_widget.model:
            return
            
        pos = event.position()
        if 0 <= pos.x() <= self.width() and 0 <= pos.y() <= self.height():
            delta = event.angleDelta().y()
            
            # 计算目标缩放值
            target_scale = self.scale
            if delta > 0:
                target_scale = min(2.0, self.scale * 1.1)
            else:
                target_scale = max(0.5, self.scale * 0.9)
                
            # 如果缩放值变化不大，则不进行动画
            if abs(target_scale - self.scale) < 0.01:
                return
                
            # 计算新的窗口大小
            new_width = int(self.base_width * target_scale)
            new_height = int(self.base_height * target_scale)
            
            # 保持窗口中心点不变
            center_x = self.x() + self.width() / 2
            center_y = self.y() + self.height() / 2
            new_x = int(center_x - new_width / 2)
            new_y = int(center_y - new_height / 2)
            
            # 使用动画来平滑缩放过程
            self.scale_animation.stop()
            self.scale_animation.setStartValue(self.geometry())
            self.scale_animation.setEndValue(QRect(new_x, new_y, new_width, new_height))
            self.scale_animation.start()
            
            self.scale = target_scale
            
    def closeEvent(self, event):
        """关闭窗口时清理资源"""
        if self.chat_window:
            self.chat_window.close()
        if hasattr(self, 'ollama_thread') and self.ollama_thread:
            self.ollama_thread.quit()
            self.ollama_thread.wait()
        super().closeEvent(event)

class ControlPanel(QMainWindow):
    def __init__(self, live2d_window):
        super().__init__()
        self.live2d_window = live2d_window
        self.voice_thread = None
        self.chat_tts_thread = None
        self.test_tts = None
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
            "batch_size": 1,
            "batch_threshold": 0.75,
            "split_bucket": False,
            "return_fragment": False,
            "speed_factor": 1.0,
            "streaming_mode": True,
            "seed": -1,
            "parallel_infer": True,
            "repetition_penalty": 1.35
        }
        self.initUI()
        self.updateAudioDevices()
        self.updateLLMModels()
        
        # 初始化语音识别语言选项
        self.STT_language_combo.addItems(["zh", "en", "ja", "ko", "de", "fr"])
        
    def updateLLMModels(self):
        """更新Ollama模型列表"""
        try:
            models = ollama.list()
            model_names = [model['model'] for model in models['models']]
            model_names.insert(0, "deepseek-chat")
            self.chat_model_combo.clear()
            self.chat_model_combo.addItems(model_names)
        except Exception as e:
            print(f"获取Ollama模型列表失败: {str(e)}")
            
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
        self.prompt_edit.setMaximumHeight(100)
        self.prompt_edit.setPlaceholderText("输入系统提示词...")
        chat_group_layout.addWidget(self.prompt_edit)
        
        # 更新模型列表按钮
        update_models_btn = QPushButton("更新模型列表")
        update_models_btn.clicked.connect(self.updateLLMModels)
        chat_group_layout.addWidget(update_models_btn)
        
        chat_group.setLayout(chat_group_layout)
        chat_layout.addWidget(chat_group)
        chat_layout.addStretch()
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
        STT_group_layout.addWidget(QLabel("唤醒词:"))
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
        self.test_model_btn = QPushButton("开始测试")
        self.test_model_btn.clicked.connect(self.testSTTModel)
        self.test_model_btn.setEnabled(False)
        STT_group_layout.addWidget(self.test_model_btn)

        # 识别结果
        STT_group_layout.addWidget(QLabel("测试识别结果:"))
        self.STT_result_label = QLabel()
        STT_group_layout.addWidget(self.STT_result_label)

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
        
        # 扬声器选择
        audio_layout = QHBoxLayout()
        audio_label = QLabel("输出设备:")
        self.TTS_audio_devices = QComboBox()
        self.TTS_audio_devices.setEnabled(True)
        audio_layout.addWidget(audio_label)
        audio_layout.addWidget(self.TTS_audio_devices)
        TTS_group_layout.addLayout(audio_layout)
        
        # Streaming Mode
        stream_layout = QHBoxLayout()
        self.stream_checkbox = QCheckBox("流式响应")
        self.stream_checkbox.setChecked(self.tts_settings["streaming_mode"])
        self.stream_checkbox.stateChanged.connect(lambda x: self.updateTTSSetting("streaming_mode", bool(x)))
        stream_layout.addWidget(self.stream_checkbox)
        stream_layout.addStretch()
        TTS_group_layout.addLayout(stream_layout)
        
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
        
        # 添加选项卡
        tab_widget.addTab(model_tab, "模型")
        tab_widget.addTab(tracking_tab, "视线")
        tab_widget.addTab(lipsync_tab, "口型")
        tab_widget.addTab(chat_tab, "对话")
        tab_widget.addTab(STT_tab, "语音识别")
        tab_widget.addTab(TTS_tab, "语音生成")
        
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
                    
                    # 加载动作和表情列表
                    self.loadMotionsAndExpressions(model_path)
                    
                    # 更新音频设备列表
                    self.updateAudioDevices()
            except Exception as e:
                print(f"加载模型失败: {str(e)}")
                
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
            
            # 清空列表
            self.motion_group_combo.clear()
            self.motion_combo.clear()
            self.expression_combo.clear()
        except Exception as e:
            print(f"卸载模型失败: {str(e)}")
            
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
            self.voice_thread = STTThread(config)
            self.voice_thread.text_signal.connect(self.handleSTTResult)
            self.voice_thread.test_signal.connect(self.handleSTTTestResult)
            self.voice_thread.STTmodel_ready_signal.connect(self.onSTTModelReady)
            self.voice_thread.set_chat_window(self.live2d_window.chat_window)
            self.voice_thread.start()
            
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
        self.test_model_btn.setEnabled(True)
        self.unload_STTmodel_btn.setEnabled(True)
        QMessageBox.information(self, "成功", "语音识别模型加载成功！")

    def unloadSTTModel(self):
        """卸载语音识别模型"""
        if self.voice_thread:
            self.voice_thread.recorder.shutdown()
            self.voice_thread.stop()
            self.voice_thread = None
        
        # 启用设置控件
        self.STT_audio_devices.setEnabled(True)
        self.STT_language_combo.setEnabled(True)
        self.STT_model_combo.setEnabled(True)
        self.STT_wake_word_edit.setEnabled(True)
        self.load_STTmodel_btn.setText("加载模型")
        self.load_STTmodel_btn.setEnabled(True)
        
        # 禁用测试和卸载按钮
        self.test_model_btn.setEnabled(False)
        self.test_model_btn.setText("开始测试")
        self.unload_STTmodel_btn.setEnabled(False)
        
        # 清空结果显示
        self.STT_result_label.setText("")

    def testSTTModel(self):
        """测试语音识别模型"""
        if not self.voice_thread:
            return
            
        if self.test_model_btn.text() == "开始测试":
            self.voice_thread.is_testing = True  # 设置为测试模式
            self.voice_thread.resume()  # 开始录音
            self.test_model_btn.setText("停止测试")
            # 清空之前的测试结果
            self.STT_result_label.clear()
        else:
            self.voice_thread.pause()  # 先暂停录音
            self.voice_thread.is_testing = False  # 关闭测试模式
            self.test_model_btn.setText("开始测试")
            # 清空测试结果
            self.STT_result_label.clear()

    def handleSTTResult(self, text):
        """处理语音识别结果"""
        if not text:
            return
        self.live2d_window.chat_window.input_box.setPlainText(text)
    def handleSTTTestResult(self, text):
        """处理语音识别测试结果"""
        if not text:
            return
        self.STT_result_label.setText(text)

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
        

        
            
def main():
    app = QApplication(sys.argv)
    
    # 设置OpenGL格式
    format = QSurfaceFormat()
    format.setVersion(2, 1)  # 使用OpenGL 2.1
    format.setProfile(QSurfaceFormat.OpenGLContextProfile.NoProfile)
    format.setDepthBufferSize(24)
    format.setStencilBufferSize(8)
    format.setSwapBehavior(QSurfaceFormat.SwapBehavior.DoubleBuffer)
    format.setAlphaBufferSize(8)
    QSurfaceFormat.setDefaultFormat(format)
    
    try:
        live2d_window = Live2DWindow()
        control_panel = ControlPanel(live2d_window)
        live2d_window.control_panel = control_panel
        live2d_window.chat_window.control_panel = control_panel
        
        live2d_window.show()
        control_panel.show()
        
        return app.exec()
    finally:
        # 确保在程序退出时清理资源
        if 'live2d_window' in locals():
            live2d_window.close()

if __name__ == '__main__':
    main()
