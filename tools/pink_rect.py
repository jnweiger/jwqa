#! /usr/bin/python3
#
# 
# Requires:
#   pip install PyQt5
#
# Usage:
#         hook into gnome with hotkey Alt + Q
#
#         Left Click: Starts the rectangle.
#         Drag: Resizes the rectangle.
#         Left Click (again): Finalizes the rectangle. It stays visible for 2 seconds and then fades out.
#         Right Click or Any other key: Aborts the operation immediately.
# 
# Cursor: The custom cursor is drawn as a white circle. If it's hard to see on a light background,
#   you can change the QColor(255, 255, 255, 200) to a darker color like QColor(0, 0, 0, 200).
# 

import sys, os, time

# --- CRITICAL: Detect Session Type BEFORE importing Qt ---
# If WAYLAND_DISPLAY is set, we are on Wayland. Otherwise, assume X11.
if os.environ.get('XDG_SESSION_TYPE', "") == 'wayland':
    del os.environ['XDG_SESSION_TYPE']

from PyQt5.QtWidgets import QApplication, QWidget
from PyQt5.QtGui import QPainter, QColor, QPen, QCursor, QPixmap
from PyQt5.QtCore import Qt, QRect, QTimer, QPoint

class DrawingOverlay(QWidget):
    def __init__(self):
        super().__init__()
        
        # 1. Window Setup: Transparent, Borderless, Always on Top
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # 2. Full Screen
        screen_size = QApplication.primaryScreen().size()
        self.setGeometry(0, 0, screen_size.width(), screen_size.height())
        
        # 3. State
        self.mode = "DRAGGING"
        self.start_point = None
        self.current_point = None
        self.final_rect = None
        self.alpha = 255
        self.fade_timer = None
        self.fade_start_time = 0
        
        # 4. Custom Cursor (Hollow Circle)
        self._create_custom_cursor()
        self.original_cursor = QCursor()
        
        # 5. Show and Set Cursor
        self.show()
        self.setCursor(self.custom_cursor)

        # self.setFocusPolicy(Qt.StrongFocus)
        # 6. CRITICAL: Force Focus Immediately
        # This ensures the window receives keyboard events before any mouse click
        self.activateWindow()
        self.raise_()
        self.setFocus(Qt.ActiveWindowFocusReason)
        self.grabKeyboard()

        # 7. Connect Mouse Events
        self.mousePressEvent = self.on_mouse_press
        self.mouseMoveEvent = self.on_mouse_move
        self.mouseReleaseEvent = self.on_mouse_release


    def _create_custom_cursor(self):
        size = 40
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Hollow Circle: No Fill, Pink Border
        painter.setBrush(Qt.NoBrush) 
        painter.setPen(QPen(QColor(255, 105, 180), 2)) # Pink border
        painter.drawEllipse(2, 2, size - 4, size - 4)
        
        painter.end()
        self.custom_cursor = QCursor(pixmap, size // 2, size // 2)

    def keyPressEvent(self, event):
        # Exit immediately on ANY key press
        self.close_overlay()

    def on_mouse_press(self, event):
        if event.button() == Qt.LeftButton:
            if self.start_point is None:
                # First Click: Start Drag
                self.start_point = event.pos()
                self.current_point = event.pos()
            else:
                # Second Click: Finish
                self.final_rect = QRect(
                    min(self.start_point.x(), self.current_point.x()),
                    min(self.start_point.y(), self.current_point.y()),
                    abs(self.current_point.x() - self.start_point.x()),
                    abs(self.current_point.y() - self.start_point.y())
                )
                self.mode = "FINISHED"
                self.update()
                self.fade_start_time = time.time()
                if not self.fade_timer:
                    self.fade_timer = QTimer()
                    self.fade_timer.timeout.connect(self.update_fade)
                self.fade_timer.start(20)
                if self.original_cursor:
                    self.setCursor(self.original_cursor)
                    self.original_cursor = None
        elif event.button() == Qt.RightButton:
            # Abort on Right Click
            self.close_overlay()

    def on_mouse_move(self, event):
        if self.mode == "DRAGGING" and self.start_point:
            self.current_point = event.pos()
            self.update()

    def on_mouse_release(self, event):
        if self.original_cursor:
            self.setCursor(self.original_cursor)
        self.original_cursor = None

    def update_fade(self):
        # Fade out in 0.5 seconds
        elapsed = time.time() - self.fade_start_time
        if elapsed > 0.5:
            self.close_overlay()
        else:
            self.alpha = int(255 * (1.0 - (elapsed / 0.5)))
            self.update()

    def close_overlay(self):
        # Restore normal cursor BEFORE closing
        if self.original_cursor:
            self.setCursor(self.original_cursor)
        if self.fade_timer:
            self.fade_timer.stop()
        self.close()
        QApplication.quit()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        if self.mode in ["DRAGGING", "FINISHED"]:
            rect = None
            if self.mode == "DRAGGING" and self.start_point and self.current_point:
                rect = QRect(
                    min(self.start_point.x(), self.current_point.x()),
                    min(self.start_point.y(), self.current_point.y()),
                    abs(self.current_point.x() - self.start_point.x()),
                    abs(self.current_point.y() - self.start_point.y())
                )
            elif self.mode == "FINISHED" and self.final_rect:
                rect = self.final_rect
            
            if rect:
                # No Fill
                painter.setBrush(Qt.NoBrush)
                
                # 2px Pink Line with Alpha
                pen = QPen(QColor(255, 105, 180, self.alpha), 2)
                painter.setPen(pen)
                painter.drawRect(rect)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    overlay = DrawingOverlay()
    sys.exit(app.exec_())

