from typing import Optional
from PyQt6.QtWidgets import ( QMainWindow, QPushButton, QVBoxLayout, 
                           QHBoxLayout, QWidget, 
                           QTextEdit, QMenu, QPlainTextEdit)
from PyQt6.QtCore import Qt, QTimer, QPoint, QRect, QPropertyAnimation, QTime
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from PyQt6.QtGui import  QCursor
from OpenGL.GL import *
import live2d.v3 as live2d
from mic_lipsync import MicLipSync
from LLM import LLMThread

#opengl-live2d窗口
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

#live2d窗口
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
        
        # 移动相关
        self.is_moving = False

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
        # if self.chat_window:
        #     self.chat_window.close()
        super().closeEvent(event)