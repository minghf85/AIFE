import sys
from PyQt6.QtGui import QSurfaceFormat
from PyQt6.QtWidgets import QApplication

from Live2DWindow import Live2DWindow
from ControlPanel import ControlPanel

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
        
        live2d_window.show()
        control_panel.show()
        
        return app.exec()
    finally:
        # 确保在程序退出时清理资源
        if 'live2d_window' in locals():
            live2d_window.close()

if __name__ == '__main__':
    main()
