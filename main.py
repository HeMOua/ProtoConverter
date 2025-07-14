import sys
import os
import subprocess
from pathlib import Path
from PyQt6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, 
                            QWidget, QPushButton, QLabel, QLineEdit, QTextEdit, 
                            QFileDialog, QCheckBox, QGroupBox, QProgressBar, 
                            QMessageBox, QComboBox, QGridLayout, QTabWidget)
from PyQt6.QtCore import QThread, pyqtSignal, Qt
from PyQt6.QtGui import QFont, QIcon


class ProtocWorker(QThread):
    """后台线程处理protoc编译"""
    progress = pyqtSignal(str)
    finished = pyqtSignal(bool, str)
    
    def __init__(self, proto_files, output_dir, generate_java, generate_python, 
                 generate_python_grpc, protoc_path="protoc", include_paths=None):
        super().__init__()
        self.proto_files = proto_files
        self.output_dir = output_dir
        self.generate_java = generate_java
        self.generate_python = generate_python
        self.generate_python_grpc = generate_python_grpc
        self.protoc_path = protoc_path
        self.include_paths = include_paths or []
    
    def run(self):
        try:
            success_count = 0
            total_files = len(self.proto_files)
            
            for i, proto_file in enumerate(self.proto_files):
                self.progress.emit(f"正在处理: {os.path.basename(proto_file)} ({i+1}/{total_files})")
                
                # 准备include路径参数
                include_args = []
                
                # 添加proto文件所在目录
                proto_dir = os.path.dirname(proto_file)
                if proto_dir:
                    include_args.append(f"--proto_path={proto_dir}")
                
                # 添加自定义include路径
                for include_path in self.include_paths:
                    include_args.append(f"--proto_path={include_path}")
                
                # 如果没有include路径，添加当前目录
                if not include_args:
                    include_args.append("--proto_path=.")
                
                if self.generate_java:
                    java_output = os.path.join(self.output_dir, "java")
                    os.makedirs(java_output, exist_ok=True)
                    
                    java_cmd = [
                        self.protoc_path,
                        f"--java_out={java_output}",
                        *include_args,
                        proto_file
                    ]
                    
                    self.progress.emit(f"生成Java代码: {os.path.basename(proto_file)}")
                    result = subprocess.run(java_cmd, capture_output=True, text=True)
                    if result.returncode != 0:
                        self.finished.emit(False, f"Java生成失败: {result.stderr}")
                        return
                
                if self.generate_python or self.generate_python_grpc:
                    python_output = os.path.join(self.output_dir, "python")
                    os.makedirs(python_output, exist_ok=True)
                    
                    # 使用grpcio-tools生成Python代码
                    if self.generate_python_grpc:
                        # 生成包含gRPC的完整Python代码
                        self.progress.emit(f"生成Python + gRPC代码: {os.path.basename(proto_file)}")
                        success = self._generate_python_with_grpc(proto_file, python_output, include_args)
                    else:
                        # 只生成基本的Python protobuf代码
                        self.progress.emit(f"生成Python代码: {os.path.basename(proto_file)}")
                        success = self._generate_python_only(proto_file, python_output, include_args)
                    
                    if not success:
                        return
                
                success_count += 1
            
            self.finished.emit(True, f"成功处理 {success_count} 个文件")
            
        except Exception as e:
            self.finished.emit(False, f"处理过程中出错: {str(e)}")
    
    def _generate_python_with_grpc(self, proto_file, output_dir, include_args):
        """使用grpcio-tools生成Python + gRPC代码"""
        try:
            # 构建grpc_tools.protoc命令
            cmd = [
                sys.executable, "-m", "grpc_tools.protoc",
                f"--python_out={output_dir}",
                f"--grpc_python_out={output_dir}",
                *include_args,
                proto_file
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                self.finished.emit(False, f"Python gRPC生成失败: {result.stderr}")
                return False
            
            return True
            
        except Exception as e:
            self.finished.emit(False, f"Python gRPC生成出错: {str(e)}")
            return False
    
    def _generate_python_only(self, proto_file, output_dir, include_args):
        """只生成基本的Python protobuf代码"""
        try:
            # 使用grpc_tools.protoc但只生成python_out
            cmd = [
                sys.executable, "-m", "grpc_tools.protoc",
                f"--python_out={output_dir}",
                *include_args,
                proto_file
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                self.finished.emit(False, f"Python生成失败: {result.stderr}")
                return False
            
            return True
            
        except Exception as e:
            self.finished.emit(False, f"Python生成出错: {str(e)}")
            return False


class ProtoConverterGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.proto_files = []
        self.include_paths = []
        self.worker = None
        self.init_ui()
        
    def init_ui(self):
        self.setWindowTitle("Proto文件转换工具 (增强版)")
        self.setGeometry(100, 100, 900, 700)
        
        # 创建中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 创建主布局
        main_layout = QVBoxLayout(central_widget)
        
        # 标题
        title = QLabel("Protocol Buffers 代码生成工具 (grpcio-tools)")
        title.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(title)
        
        # 创建选项卡
        tab_widget = QTabWidget()
        main_layout.addWidget(tab_widget)
        
        # 基本配置选项卡
        basic_tab = QWidget()
        tab_widget.addTab(basic_tab, "基本配置")
        self.init_basic_tab(basic_tab)
        
        # 高级配置选项卡
        advanced_tab = QWidget()
        tab_widget.addTab(advanced_tab, "高级配置")
        self.init_advanced_tab(advanced_tab)
        
        # 控制按钮
        button_layout = QHBoxLayout()
        
        self.convert_btn = QPushButton("开始转换")
        self.convert_btn.clicked.connect(self.start_conversion)
        self.convert_btn.setStyleSheet("QPushButton { background-color: #4CAF50; color: white; font-weight: bold; }")
        button_layout.addWidget(self.convert_btn)
        
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self.cancel_conversion)
        self.cancel_btn.setEnabled(False)
        button_layout.addWidget(self.cancel_btn)
        
        open_output_btn = QPushButton("打开输出目录")
        open_output_btn.clicked.connect(self.open_output_dir)
        button_layout.addWidget(open_output_btn)
        
        # 检查依赖按钮
        check_deps_btn = QPushButton("检查Python依赖")
        check_deps_btn.clicked.connect(self.check_python_dependencies)
        button_layout.addWidget(check_deps_btn)
        
        main_layout.addLayout(button_layout)
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)
        
        # 日志输出
        log_group = QGroupBox("输出日志")
        log_layout = QVBoxLayout(log_group)
        
        self.log_text = QTextEdit()
        self.log_text.setMaximumHeight(150)
        self.log_text.setReadOnly(True)
        log_layout.addWidget(self.log_text)
        
        main_layout.addWidget(log_group)
        
        # 设置默认输出目录
        self.output_dir_edit.setText(os.path.join(os.getcwd(), "proto_output"))
    
    def init_basic_tab(self, tab_widget):
        """初始化基本配置选项卡"""
        layout = QVBoxLayout(tab_widget)
        
        # Protoc路径配置
        protoc_group = QGroupBox("Protoc配置")
        protoc_layout = QHBoxLayout(protoc_group)
        
        protoc_layout.addWidget(QLabel("Protoc路径:"))
        self.protoc_path_edit = QLineEdit("protoc")
        self.protoc_path_edit.setToolTip("protoc编译器的路径，默认使用系统PATH中的protoc")
        protoc_layout.addWidget(self.protoc_path_edit)
        
        protoc_browse_btn = QPushButton("浏览")
        protoc_browse_btn.clicked.connect(self.browse_protoc)
        protoc_layout.addWidget(protoc_browse_btn)
        
        test_protoc_btn = QPushButton("测试")
        test_protoc_btn.clicked.connect(self.test_protoc)
        protoc_layout.addWidget(test_protoc_btn)
        
        layout.addWidget(protoc_group)
        
        # Proto文件选择
        file_group = QGroupBox("Proto文件选择")
        file_layout = QVBoxLayout(file_group)
        
        file_btn_layout = QHBoxLayout()
        add_files_btn = QPushButton("添加Proto文件")
        add_files_btn.clicked.connect(self.add_proto_files)
        file_btn_layout.addWidget(add_files_btn)
        
        add_folder_btn = QPushButton("添加文件夹")
        add_folder_btn.clicked.connect(self.add_proto_folder)
        file_btn_layout.addWidget(add_folder_btn)
        
        clear_files_btn = QPushButton("清空列表")
        clear_files_btn.clicked.connect(self.clear_proto_files)
        file_btn_layout.addWidget(clear_files_btn)
        
        file_layout.addLayout(file_btn_layout)
        
        # 文件列表
        self.file_list = QTextEdit()
        self.file_list.setMaximumHeight(120)
        self.file_list.setReadOnly(True)
        file_layout.addWidget(self.file_list)
        
        layout.addWidget(file_group)
        
        # 输出配置
        output_group = QGroupBox("输出配置")
        output_layout = QGridLayout(output_group)
        
        # 输出目录
        output_layout.addWidget(QLabel("输出目录:"), 0, 0)
        self.output_dir_edit = QLineEdit()
        output_layout.addWidget(self.output_dir_edit, 0, 1)
        
        output_browse_btn = QPushButton("浏览")
        output_browse_btn.clicked.connect(self.browse_output_dir)
        output_layout.addWidget(output_browse_btn, 0, 2)
        
        # 生成选项
        self.java_checkbox = QCheckBox("生成Java代码")
        self.java_checkbox.setChecked(True)
        output_layout.addWidget(self.java_checkbox, 1, 0)
        
        self.python_checkbox = QCheckBox("生成Python代码")
        self.python_checkbox.setChecked(True)
        output_layout.addWidget(self.python_checkbox, 1, 1)
        
        self.python_grpc_checkbox = QCheckBox("生成Python gRPC代码")
        self.python_grpc_checkbox.setChecked(True)
        self.python_grpc_checkbox.setToolTip("使用grpcio-tools生成包含gRPC服务的Python代码")
        output_layout.addWidget(self.python_grpc_checkbox, 1, 2)
        
        layout.addWidget(output_group)
    
    def init_advanced_tab(self, tab_widget):
        """初始化高级配置选项卡"""
        layout = QVBoxLayout(tab_widget)
        
        # Include路径配置
        include_group = QGroupBox("Include路径配置")
        include_layout = QVBoxLayout(include_group)
        
        include_btn_layout = QHBoxLayout()
        add_include_btn = QPushButton("添加Include路径")
        add_include_btn.clicked.connect(self.add_include_path)
        include_btn_layout.addWidget(add_include_btn)
        
        clear_include_btn = QPushButton("清空Include路径")
        clear_include_btn.clicked.connect(self.clear_include_paths)
        include_btn_layout.addWidget(clear_include_btn)
        
        include_btn_layout.addStretch()
        include_layout.addLayout(include_btn_layout)
        
        # Include路径列表
        self.include_list = QTextEdit()
        self.include_list.setMaximumHeight(100)
        self.include_list.setReadOnly(True)
        self.include_list.setPlaceholderText("包含proto文件依赖的目录路径...")
        include_layout.addWidget(self.include_list)
        
        layout.addWidget(include_group)
        
        # Python特定配置
        python_group = QGroupBox("Python生成配置")
        python_layout = QGridLayout(python_group)
        
        python_layout.addWidget(QLabel("Python解释器:"), 0, 0)
        self.python_interpreter_edit = QLineEdit(sys.executable)
        python_layout.addWidget(self.python_interpreter_edit, 0, 1)
        
        python_browse_btn = QPushButton("浏览")
        python_browse_btn.clicked.connect(self.browse_python_interpreter)
        python_layout.addWidget(python_browse_btn, 0, 2)
        
        # 验证grpcio-tools是否安装
        self.grpc_tools_status = QLabel("检查中...")
        python_layout.addWidget(QLabel("grpcio-tools状态:"), 1, 0)
        python_layout.addWidget(self.grpc_tools_status, 1, 1)
        
        install_grpc_btn = QPushButton("安装grpcio-tools")
        install_grpc_btn.clicked.connect(self.install_grpcio_tools)
        python_layout.addWidget(install_grpc_btn, 1, 2)
        
        layout.addWidget(python_group)
        
        # 代码生成示例
        example_group = QGroupBox("生成代码示例")
        example_layout = QVBoxLayout(example_group)
        
        self.example_text = QTextEdit()
        self.example_text.setReadOnly(True)
        self.example_text.setMaximumHeight(200)
        self.example_text.setPlainText(self.get_usage_examples())
        example_layout.addWidget(self.example_text)
        
        layout.addWidget(example_group)
        
        layout.addStretch()
        
        # 初始检查grpcio-tools状态
        self.check_grpcio_tools_status()
    
    def get_usage_examples(self):
        """返回使用示例文本"""
        return """生成的Python代码使用示例:

# 基本使用
import example_pb2

# 创建消息对象
person = example_pb2.Person()
person.name = "张三"
person.id = 123
person.email = "zhangsan@example.com"

# 序列化
data = person.SerializeToString()

# 反序列化
new_person = example_pb2.Person()
new_person.ParseFromString(data)

# gRPC服务使用 (如果生成了gRPC代码)
import example_pb2_grpc
import grpc

channel = grpc.insecure_channel('localhost:50051')
stub = example_pb2_grpc.PersonServiceStub(channel)

request = example_pb2.GetPersonRequest(id=123)
response = stub.GetPerson(request)
"""
    
    def browse_protoc(self):
        """浏览protoc可执行文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择Protoc可执行文件", "", 
            "可执行文件 (*.exe);;所有文件 (*.*)"
        )
        if file_path:
            self.protoc_path_edit.setText(file_path)
    
    def browse_python_interpreter(self):
        """浏览Python解释器"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择Python解释器", "", 
            "可执行文件 (python.exe python);;所有文件 (*.*)"
        )
        if file_path:
            self.python_interpreter_edit.setText(file_path)
    
    def test_protoc(self):
        """测试protoc是否可用"""
        protoc_path = self.protoc_path_edit.text()
        try:
            result = subprocess.run([protoc_path, "--version"], 
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                version = result.stdout.strip()
                self.log_message(f"✓ Protoc测试成功: {version}")
                QMessageBox.information(self, "测试成功", f"Protoc可用\n{version}")
            else:
                self.log_message(f"✗ Protoc测试失败: {result.stderr}")
                QMessageBox.warning(self, "测试失败", f"Protoc不可用\n{result.stderr}")
        except Exception as e:
            self.log_message(f"✗ Protoc测试失败: {str(e)}")
            QMessageBox.warning(self, "测试失败", f"无法执行Protoc\n{str(e)}")
    
    def check_grpcio_tools_status(self):
        """检查grpcio-tools是否安装"""
        try:
            python_exe = self.python_interpreter_edit.text()
            result = subprocess.run([python_exe, "-c", "import grpc_tools.protoc; print('OK')"], 
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                self.grpc_tools_status.setText("✓ 已安装")
                self.grpc_tools_status.setStyleSheet("color: green;")
            else:
                self.grpc_tools_status.setText("✗ 未安装")
                self.grpc_tools_status.setStyleSheet("color: red;")
        except Exception as e:
            self.grpc_tools_status.setText("✗ 检查失败")
            self.grpc_tools_status.setStyleSheet("color: red;")
    
    def install_grpcio_tools(self):
        """安装grpcio-tools"""
        reply = QMessageBox.question(
            self, "安装确认", 
            "是否要安装grpcio-tools?\n这可能需要几分钟时间。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                python_exe = self.python_interpreter_edit.text()
                self.log_message("正在安装grpcio-tools...")
                
                # 在后台安装
                result = subprocess.run([python_exe, "-m", "pip", "install", "grpcio-tools"], 
                                      capture_output=True, text=True, timeout=120)
                
                if result.returncode == 0:
                    self.log_message("✓ grpcio-tools安装成功")
                    self.check_grpcio_tools_status()
                    QMessageBox.information(self, "安装成功", "grpcio-tools已成功安装!")
                else:
                    self.log_message(f"✗ grpcio-tools安装失败: {result.stderr}")
                    QMessageBox.warning(self, "安装失败", f"安装失败:\n{result.stderr}")
                    
            except Exception as e:
                self.log_message(f"✗ 安装过程出错: {str(e)}")
                QMessageBox.critical(self, "安装错误", f"安装过程出错:\n{str(e)}")
    
    def check_python_dependencies(self):
        """检查Python依赖"""
        python_exe = self.python_interpreter_edit.text()
        dependencies = ["protobuf", "grpcio", "grpcio-tools"]
        
        results = []
        for dep in dependencies:
            try:
                result = subprocess.run([python_exe, "-c", f"import {dep.replace('-', '_')}; print('OK')"], 
                                      capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    results.append(f"✓ {dep}: 已安装")
                else:
                    results.append(f"✗ {dep}: 未安装")
            except Exception:
                results.append(f"✗ {dep}: 检查失败")
        
        message = "Python依赖检查结果:\n\n" + "\n".join(results)
        QMessageBox.information(self, "依赖检查", message)
    
    def add_include_path(self):
        """添加include路径"""
        directory = QFileDialog.getExistingDirectory(self, "选择Include目录")
        if directory and directory not in self.include_paths:
            self.include_paths.append(directory)
            self.update_include_list()
    
    def clear_include_paths(self):
        """清空include路径"""
        self.include_paths.clear()
        self.update_include_list()
    
    def update_include_list(self):
        """更新include路径列表显示"""
        if self.include_paths:
            path_text = "\n".join([f"• {path}" for path in self.include_paths])
            self.include_list.setText(path_text)
        else:
            self.include_list.setText("未设置include路径")
    
    def add_proto_files(self):
        """添加Proto文件"""
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择Proto文件", "", "Proto文件 (*.proto);;所有文件 (*.*)"
        )
        for file in files:
            if file not in self.proto_files:
                self.proto_files.append(file)
        self.update_file_list()
    
    def add_proto_folder(self):
        """添加包含Proto文件的文件夹"""
        folder = QFileDialog.getExistingDirectory(self, "选择包含Proto文件的文件夹")
        if folder:
            proto_files = list(Path(folder).glob("**/*.proto"))
            for file in proto_files:
                file_str = str(file)
                if file_str not in self.proto_files:
                    self.proto_files.append(file_str)
            self.update_file_list()
    
    def clear_proto_files(self):
        """清空Proto文件列表"""
        self.proto_files.clear()
        self.update_file_list()
    
    def update_file_list(self):
        """更新文件列表显示"""
        if self.proto_files:
            file_text = "\n".join([f"• {os.path.basename(f)} ({f})" for f in self.proto_files])
            self.file_list.setText(file_text)
        else:
            self.file_list.setText("未选择任何Proto文件")
    
    def browse_output_dir(self):
        """选择输出目录"""
        directory = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if directory:
            self.output_dir_edit.setText(directory)
    
    def start_conversion(self):
        """开始转换"""
        # 验证输入
        if not self.proto_files:
            QMessageBox.warning(self, "错误", "请选择至少一个Proto文件")
            return
        
        output_dir = self.output_dir_edit.text()
        if not output_dir:
            QMessageBox.warning(self, "错误", "请选择输出目录")
            return
        
        generate_java = self.java_checkbox.isChecked()
        generate_python = self.python_checkbox.isChecked()
        generate_python_grpc = self.python_grpc_checkbox.isChecked()
        
        if not generate_java and not generate_python and not generate_python_grpc:
            QMessageBox.warning(self, "错误", "请至少选择一种生成选项")
            return
        
        # 如果选择了Python gRPC，检查grpcio-tools
        if generate_python_grpc:
            python_exe = self.python_interpreter_edit.text()
            try:
                result = subprocess.run([python_exe, "-c", "import grpc_tools.protoc"], 
                                      capture_output=True, text=True, timeout=5)
                if result.returncode != 0:
                    reply = QMessageBox.question(
                        self, "缺少依赖", 
                        "grpcio-tools未安装，是否现在安装？",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                    )
                    if reply == QMessageBox.StandardButton.Yes:
                        self.install_grpcio_tools()
                        return
                    else:
                        return
            except Exception:
                QMessageBox.warning(self, "错误", "无法检查grpcio-tools状态")
                return
        
        # 创建输出目录
        os.makedirs(output_dir, exist_ok=True)
        
        # 启动后台线程
        self.worker = ProtocWorker(
            self.proto_files,
            output_dir,
            generate_java,
            generate_python,
            generate_python_grpc,
            self.protoc_path_edit.text(),
            self.include_paths
        )
        
        self.worker.progress.connect(self.update_progress)
        self.worker.finished.connect(self.conversion_finished)
        
        # 更新UI状态
        self.convert_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # 不确定进度
        
        self.log_message("开始转换...")
        self.worker.start()
    
    def cancel_conversion(self):
        """取消转换"""
        if self.worker and self.worker.isRunning():
            self.worker.terminate()
            self.worker.wait()
            self.log_message("转换已取消")
        
        self.reset_ui_state()
    
    def update_progress(self, message):
        """更新进度信息"""
        self.log_message(message)
    
    def conversion_finished(self, success, message):
        """转换完成"""
        self.reset_ui_state()
        
        if success:
            self.log_message(f"✓ {message}")
            # 显示生成的文件结构
            self.show_generated_files()
            QMessageBox.information(self, "转换完成", message)
        else:
            self.log_message(f"✗ {message}")
            QMessageBox.critical(self, "转换失败", message)
    
    def show_generated_files(self):
        """显示生成的文件结构"""
        output_dir = self.output_dir_edit.text()
        if not os.path.exists(output_dir):
            return
        
        self.log_message("\n生成的文件结构:")
        for root, dirs, files in os.walk(output_dir):
            level = root.replace(output_dir, '').count(os.sep)
            indent = ' ' * 2 * level
            self.log_message(f"{indent}{os.path.basename(root)}/")
            subindent = ' ' * 2 * (level + 1)
            for file in files:
                self.log_message(f"{subindent}{file}")
    
    def reset_ui_state(self):
        """重置UI状态"""
        self.convert_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.progress_bar.setVisible(False)
    
    def open_output_dir(self):
        """打开输出目录"""
        output_dir = self.output_dir_edit.text()
        if output_dir and os.path.exists(output_dir):
            if sys.platform == "win32":
                os.startfile(output_dir)
            elif sys.platform == "darwin":
                subprocess.run(["open", output_dir])
            else:
                subprocess.run(["xdg-open", output_dir])
        else:
            QMessageBox.warning(self, "错误", "输出目录不存在")
    
    def log_message(self, message):
        """添加日志消息"""
        self.log_text.append(f"[{self.get_timestamp()}] {message}")
        self.log_text.ensureCursorVisible()
    
    def get_timestamp(self):
        """获取当前时间戳"""
        from datetime import datetime
        return datetime.now().strftime("%H:%M:%S")


def main():
    app = QApplication(sys.argv)
    
    # 设置应用信息
    app.setApplicationName("Proto转换工具 (增强版)")
    app.setApplicationVersion("2.0")
    
    # 创建并显示主窗口
    window = ProtoConverterGUI()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()