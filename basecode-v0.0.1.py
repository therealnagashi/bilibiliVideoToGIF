# Bilibili视频转GIF工具By:樱流
# 支持下载bilibili视频并转换为GIF动图，新增本地视频上传功能
# 新增功能：自动识别和移除黑边、bilibili水印，支持本地视频文件
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import sys
import subprocess
import threading
import time
import json
import logging
import locale
from pathlib import Path
import re
from urllib.parse import urlparse
import numpy as np

# 显示控制台窗口
if os.name == 'nt':  # Windows系统
    import ctypes
    try:
        # 分配新的控制台
        ctypes.windll.kernel32.AllocConsole()
        # 重定向标准输出到控制台
        sys.stdout = open('CONOUT$', 'w', encoding='utf-8')
        sys.stderr = open('CONOUT$', 'w', encoding='utf-8')
        print("控制台已启用")
    except:
        pass

class LibraryInstaller:
    """库安装器"""
    
    # 格式: (安装包名, 导入名)
    REQUIRED_PACKAGES = [
        ('yt-dlp', 'yt_dlp'),
        ('Pillow', 'PIL'),
        ('requests', 'requests'),
        ('opencv-python', 'cv2'),
        ('numpy', 'numpy')
    ]
    
    CHINA_MIRRORS = [
        'https://pypi.tuna.tsinghua.edu.cn/simple/',
        'https://mirrors.aliyun.com/pypi/simple/',
        'https://pypi.mirrors.ustc.edu.cn/simple/',
        'https://pypi.douban.com/simple/'
    ]
    
    @classmethod
    def check_and_install_packages(cls):
        """检查并安装所需包"""
        missing_packages = []
        
        for install_name, import_name in cls.REQUIRED_PACKAGES:
            try:
                __import__(import_name)
                print(f"✓ {install_name} 已安装")
            except ImportError:
                print(f"✗ {install_name} 未安装")
                missing_packages.append(install_name)
        
        if missing_packages:
            # 创建一个简单的对话框让用户选择
            root = tk.Tk()
            root.withdraw()  # 隐藏主窗口
            
            result = messagebox.askyesnocancel(
                "缺少依赖库", 
                f"检测到缺少以下库：{', '.join(missing_packages)}\n\n"
                f"点击'是'自动安装\n"
                f"点击'否'跳过检查继续运行\n"
                f"点击'取消'退出程序"
            )
            
            root.destroy()
            
            if result is True:  # 是 - 安装
                cls._install_packages(missing_packages)
            elif result is False:  # 否 - 跳过
                print("跳过库检查，继续运行...")
                return
            else:  # 取消 - 退出
                sys.exit(1)
    
    @classmethod
    def _install_packages(cls, packages):
        """安装包"""
        for package in packages:
            success = False
            
            # 首先尝试默认源
            try:
                subprocess.check_call([
                    sys.executable, '-m', 'pip', 'install', package
                ])
                success = True
            except subprocess.CalledProcessError:
                pass
            
            # 如果失败，尝试国内镜像
            if not success:
                for mirror in cls.CHINA_MIRRORS:
                    try:
                        subprocess.check_call([
                            sys.executable, '-m', 'pip', 'install', 
                            '-i', mirror, package
                        ])
                        success = True
                        break
                    except subprocess.CalledProcessError:
                        continue
            
            if not success:
                messagebox.showerror("安装失败", f"无法安装 {package}")
                sys.exit(1)
        
        messagebox.showinfo("安装完成", "所有依赖库已安装完成，请重新启动程序")
        sys.exit(0)

# 在文件顶部导入所有需要的库
try:
    import cv2
    CV2_AVAILABLE = True
    print("✓ OpenCV 已加载")
except ImportError:
    CV2_AVAILABLE = False
    print("✗ OpenCV 未安装，智能裁切功能将受限")

class VideoProcessor:
    """视频处理器 - 负责黑边和水印检测与移除"""
    
    @staticmethod
    def detect_black_borders(frame, threshold=30):
        """检测视频帧的黑边"""
        if not CV2_AVAILABLE:
            return 0, 0, 0, 0
            
        # 转换为灰度图
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape
        
        # 检测上边黑边
        top = 0
        for i in range(h // 3):  # 只检查上三分之一
            if np.mean(gray[i, :]) > threshold:
                break
            top = i + 1
        
        # 检测下边黑边
        bottom = 0
        for i in range(h - 1, h * 2 // 3, -1):  # 只检查下三分之一
            if np.mean(gray[i, :]) > threshold:
                break
            bottom = h - i
        
        # 检测左边黑边
        left = 0
        for i in range(w // 3):  # 只检查左三分之一
            if np.mean(gray[:, i]) > threshold:
                break
            left = i + 1
        
        # 检测右边黑边
        right = 0
        for i in range(w - 1, w * 2 // 3, -1):  # 只检查右三分之一
            if np.mean(gray[:, i]) > threshold:
                break
            right = w - i
        
        return top, bottom, left, right
    
    @staticmethod
    def detect_bilibili_watermark(frame, margin_ratio=0.15):
        """检测bilibili水印位置"""
        if not CV2_AVAILABLE:
            return 0, 0, 0, 0
            
        h, w = frame.shape[:2]
        margin_h = int(h * margin_ratio)
        margin_w = int(w * margin_ratio)
        
        # 转换为HSV用于更好的颜色检测
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # bilibili水印通常是白色或浅色的
        # 检测白色区域 (HSV中V值较高)
        white_mask = cv2.inRange(hsv, (0, 0, 200), (180, 30, 255))
        
        # 也检测灰度图中的高亮区域
        _, bright_mask = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
        
        # 合并掩码
        watermark_mask = cv2.bitwise_or(white_mask, bright_mask)
        
        # 形态学操作去除噪声
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        watermark_mask = cv2.morphologyEx(watermark_mask, cv2.MORPH_CLOSE, kernel)
        watermark_mask = cv2.morphologyEx(watermark_mask, cv2.MORPH_OPEN, kernel)
        
        # 在四个边缘区域检测水印
        regions = {
            'top': watermark_mask[:margin_h, :],
            'bottom': watermark_mask[-margin_h:, :],
            'left': watermark_mask[:, :margin_w],
            'right': watermark_mask[:, -margin_w:]
        }
        
        crop_values = {'top': 0, 'bottom': 0, 'left': 0, 'right': 0}
        
        for region_name, region in regions.items():
            if region.size == 0:
                continue
                
            # 计算该区域的白色像素比例
            white_ratio = np.sum(region > 0) / region.size
            
            # 如果白色像素比例超过阈值，认为存在水印
            if white_ratio > 0.01:  # 1%的阈值
                # 寻找连续的水印区域
                if region_name == 'top':
                    # 从上往下找到最后一行有水印的位置
                    for i in range(region.shape[0] - 1, -1, -1):
                        if np.sum(region[i, :]) > region.shape[1] * 0.02:  # 该行2%像素是白色
                            crop_values['top'] = max(crop_values['top'], i + 5)  # 多裁切5像素确保完全移除
                            break
                            
                elif region_name == 'bottom':
                    # 从下往上找到最后一行有水印的位置
                    for i in range(region.shape[0]):
                        if np.sum(region[i, :]) > region.shape[1] * 0.02:
                            crop_values['bottom'] = max(crop_values['bottom'], margin_h - i + 5)
                            break
                            
                elif region_name == 'left':
                    # 从左往右找到最后一列有水印的位置
                    for i in range(region.shape[1] - 1, -1, -1):
                        if np.sum(region[:, i]) > region.shape[0] * 0.02:
                            crop_values['left'] = max(crop_values['left'], i + 5)
                            break
                            
                elif region_name == 'right':
                    # 从右往左找到最后一列有水印的位置
                    for i in range(region.shape[1]):
                        if np.sum(region[:, i]) > region.shape[0] * 0.02:
                            crop_values['right'] = max(crop_values['right'], margin_w - i + 5)
                            break
        
        return crop_values['top'], crop_values['bottom'], crop_values['left'], crop_values['right']
    
    @staticmethod
    def calculate_smart_crop(frame, remove_black_borders=True, remove_watermark=True):
        """计算智能裁切参数"""
        if not CV2_AVAILABLE:
            return 0, 0, 0, 0
            
        h, w = frame.shape[:2]
        
        # 初始化裁切值
        crop_top = crop_bottom = crop_left = crop_right = 0
        
        # 检测黑边
        if remove_black_borders:
            black_top, black_bottom, black_left, black_right = VideoProcessor.detect_black_borders(frame)
            crop_top = max(crop_top, black_top)
            crop_bottom = max(crop_bottom, black_bottom)
            crop_left = max(crop_left, black_left)
            crop_right = max(crop_right, black_right)
        
        # 检测水印
        if remove_watermark:
            mark_top, mark_bottom, mark_left, mark_right = VideoProcessor.detect_bilibili_watermark(frame)
            crop_top = max(crop_top, mark_top)
            crop_bottom = max(crop_bottom, mark_bottom)
            crop_left = max(crop_left, mark_left)
            crop_right = max(crop_right, mark_right)
        
        # 确保裁切后仍有有效图像
        min_dimension = 100  # 最小尺寸
        if w - crop_left - crop_right < min_dimension:
            # 如果水平裁切过多，按比例减少
            total_horizontal = crop_left + crop_right
            if total_horizontal > 0:
                reduction_ratio = (w - min_dimension) / total_horizontal
                crop_left = int(crop_left * reduction_ratio)
                crop_right = int(crop_right * reduction_ratio)
        
        if h - crop_top - crop_bottom < min_dimension:
            # 如果垂直裁切过多，按比例减少
            total_vertical = crop_top + crop_bottom
            if total_vertical > 0:
                reduction_ratio = (h - min_dimension) / total_vertical
                crop_top = int(crop_top * reduction_ratio)
                crop_bottom = int(crop_bottom * reduction_ratio)
        
        return crop_top, crop_bottom, crop_left, crop_right

class BilibiliToGifConverter:
    """bilibili视频转GIF转换器"""
    
    def __init__(self, root):
        self.root = root
        self.setup_directories()
        self.setup_logging()
        self.setup_gui()
        
        # 转换参数
        self.video_info = None
        self.conversion_thread = None
        self.is_converting = False
        self.is_local_file = False  # 新增：标记是否为本地文件
        self.local_file_path = None  # 新增：本地文件路径
        
    def setup_directories(self):
        """设置目录结构"""
        self.base_dir = Path(__file__).parent
        self.output_dir = self.base_dir / "output"
        self.log_dir = self.base_dir / "logs"
        self.temp_dir = self.base_dir / "temp"
        
        for dir_path in [self.output_dir, self.log_dir, self.temp_dir]:
            dir_path.mkdir(exist_ok=True)
    
    def setup_logging(self):
        """设置日志"""
        log_file = self.log_dir / f"bilibili_to_gif_{int(time.time())}.log"
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file, encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def setup_gui(self):
        """设置GUI界面"""
        self.root.title("Bilibili视频转GIF工具By:樱流")
        self.root.geometry("950x800")
        self.root.minsize(900, 750)
        self.root.resizable(True, True)
        
        # 设置高DPI适配
        try:
            from ctypes import windll
            windll.shcore.SetProcessDpiAwareness(1)
        except:
            pass
        
        # 直接创建主框架，不使用滚动条，确保所有内容在默认大小下可见
        main_frame = ttk.Frame(self.root, padding="15")
        main_frame.pack(fill="both", expand=True)
        
        # 配置网格权重
        main_frame.columnconfigure(1, weight=1)
        
        row = 0
        
        # 输入方式选择
        input_frame = ttk.LabelFrame(main_frame, text="输入方式", padding="5")
        input_frame.grid(row=row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)
        
        self.input_method_var = tk.StringVar(value="url")
        ttk.Radiobutton(input_frame, text="Bilibili链接", variable=self.input_method_var, 
                       value="url", command=self.on_input_method_change).pack(side=tk.LEFT, padx=(0, 20))
        ttk.Radiobutton(input_frame, text="本地视频文件", variable=self.input_method_var, 
                       value="file", command=self.on_input_method_change).pack(side=tk.LEFT)
        row += 1
        
        # URL输入框
        self.url_frame = ttk.Frame(main_frame)
        self.url_frame.grid(row=row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)
        self.url_frame.columnconfigure(1, weight=1)
        
        ttk.Label(self.url_frame, text="Bilibili视频链接:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.url_var = tk.StringVar()
        url_entry = ttk.Entry(self.url_frame, textvariable=self.url_var, width=60)
        url_entry.grid(row=0, column=1, sticky=(tk.W, tk.E), pady=5, padx=(10, 0))
        ttk.Button(self.url_frame, text="获取视频信息", command=self.get_video_info).grid(
            row=0, column=2, padx=(10, 0), pady=5)
        
        # 本地文件选择框
        self.file_frame = ttk.Frame(main_frame)
        self.file_frame.columnconfigure(1, weight=1)
        
        ttk.Label(self.file_frame, text="本地视频文件:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.file_path_var = tk.StringVar()
        ttk.Entry(self.file_frame, textvariable=self.file_path_var, width=60, state="readonly").grid(
            row=0, column=1, sticky=(tk.W, tk.E), pady=5, padx=(10, 0))
        ttk.Button(self.file_frame, text="选择文件", command=self.select_local_file).grid(
            row=0, column=2, padx=(10, 0), pady=5)
        
        row += 1
        
        # 视频信息显示
        self.info_text = tk.Text(main_frame, height=4, wrap=tk.WORD)
        self.info_text.grid(row=row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)
        row += 1
        
        # 时间设置框架
        time_frame = ttk.LabelFrame(main_frame, text="时间设置", padding="5")
        time_frame.grid(row=row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
        time_frame.columnconfigure(1, weight=1)
        time_frame.columnconfigure(3, weight=1)
        
        ttk.Label(time_frame, text="开始时间(秒):").grid(row=0, column=0, sticky=tk.W)
        self.start_time_var = tk.StringVar(value="0")
        ttk.Entry(time_frame, textvariable=self.start_time_var, width=10).grid(
            row=0, column=1, sticky=tk.W, padx=(5, 20)
        )
        
        ttk.Label(time_frame, text="结束时间(秒):").grid(row=0, column=2, sticky=tk.W)
        self.end_time_var = tk.StringVar(value="10")
        ttk.Entry(time_frame, textvariable=self.end_time_var, width=10).grid(
            row=0, column=3, sticky=tk.W, padx=(5, 0)
        )
        row += 1
        
        # GIF设置框架
        gif_frame = ttk.LabelFrame(main_frame, text="GIF设置", padding="5")
        gif_frame.grid(row=row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
        gif_frame.columnconfigure(1, weight=1)
        gif_frame.columnconfigure(3, weight=1)
        
        # 分辨率设置
        ttk.Label(gif_frame, text="输出分辨率:").grid(row=0, column=0, sticky=tk.W)
        self.resolution_var = tk.StringVar()
        self.resolution_combo = ttk.Combobox(
            gif_frame, textvariable=self.resolution_var, 
            values=["480x270", "640x360", "854x480", "1280x720", "自定义"], 
            state="readonly", width=20
        )
        self.resolution_combo.grid(row=0, column=1, sticky=tk.W, padx=(5, 20))
        self.resolution_combo.set("640x360")
        
        # 压缩比例显示
        self.compression_label = ttk.Label(gif_frame, text="", foreground="blue")
        self.compression_label.grid(row=0, column=2, sticky=tk.W, padx=(10, 0))
        
        # 帧率设置
        ttk.Label(gif_frame, text="帧率(FPS):").grid(row=1, column=0, sticky=tk.W, pady=(5, 0))
        self.fps_var = tk.StringVar(value="10")
        ttk.Entry(gif_frame, textvariable=self.fps_var, width=8).grid(
            row=1, column=1, sticky=tk.W, padx=(5, 20), pady=(5, 0)
        )
        
        # 质量设置
        ttk.Label(gif_frame, text="质量:").grid(row=1, column=2, sticky=tk.W, padx=(10, 0), pady=(5, 0))
        self.quality_var = tk.StringVar(value="中")
        quality_combo = ttk.Combobox(
            gif_frame, textvariable=self.quality_var,
            values=["高", "中", "低"],
            state="readonly", width=8
        )
        quality_combo.grid(row=1, column=3, sticky=tk.W, padx=(5, 0), pady=(5, 0))
        
        # 视频处理设置
        processing_frame = ttk.LabelFrame(gif_frame, text="视频优化", padding="5")
        processing_frame.grid(row=2, column=0, columnspan=4, sticky=(tk.W, tk.E), pady=(10, 0))
        
        self.auto_crop_var = tk.BooleanVar(value=True)
        auto_crop_check = ttk.Checkbutton(
            processing_frame, 
            text="自动去除黑边", 
            variable=self.auto_crop_var
        )
        auto_crop_check.pack(side=tk.LEFT, padx=(0, 20))
        
        self.remove_watermark_var = tk.BooleanVar(value=True)
        watermark_check = ttk.Checkbutton(
            processing_frame, 
            text="智能裁切bilibili水印", 
            variable=self.remove_watermark_var
        )
        watermark_check.pack(side=tk.LEFT, padx=(0, 20))
        
        # 添加水印位置说明
        watermark_info = ttk.Label(
            processing_frame, 
            text="(自动识别右下角水印区域)",
            font=('TkDefaultFont', 8),
            foreground='gray'
        )
        watermark_info.pack(side=tk.LEFT)
        
        # 如果OpenCV不可用，显示警告并禁用智能处理选项
        if not CV2_AVAILABLE:
            auto_crop_check.config(state=tk.DISABLED)
            watermark_check.config(state=tk.DISABLED)
            self.auto_crop_var.set(False)
            self.remove_watermark_var.set(False)
            
            warning_label = ttk.Label(
                processing_frame,
                text="(需要安装opencv-python库可用智能处理)",
                font=('TkDefaultFont', 8),
                foreground='red'
            )
            warning_label.pack(side=tk.LEFT, padx=(10, 0))
        
        # 智能推荐框架
        self.recommend_frame = ttk.LabelFrame(gif_frame, text="智能推荐", padding="5")
        self.recommend_frame.grid(row=3, column=0, columnspan=4, sticky=(tk.W, tk.E), pady=(10, 0))
        self.recommend_frame.columnconfigure(0, weight=1)
        
        # 推荐信息显示
        self.recommend_text = tk.Text(self.recommend_frame, height=3, wrap=tk.WORD)
        self.recommend_text.grid(row=0, column=0, sticky=(tk.W, tk.E))
        self.recommend_text.insert(1.0, "请先获取视频信息以查看智能推荐")
        self.recommend_text.config(state=tk.DISABLED)
        
        # 推荐按钮框架
        recommend_btn_frame = ttk.Frame(self.recommend_frame)
        recommend_btn_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(5, 0))
        
        self.recommend_buttons = []
        
        # 自定义分辨率
        self.custom_frame = ttk.Frame(gif_frame)
        self.custom_frame.grid(row=4, column=0, columnspan=4, sticky=(tk.W, tk.E), pady=5)
        
        ttk.Label(self.custom_frame, text="自定义宽度:").pack(side=tk.LEFT)
        self.custom_width_var = tk.StringVar(value="640")
        ttk.Entry(self.custom_frame, textvariable=self.custom_width_var, width=8).pack(
            side=tk.LEFT, padx=(5, 20)
        )
        
        ttk.Label(self.custom_frame, text="高度:").pack(side=tk.LEFT)
        self.custom_height_var = tk.StringVar(value="360")
        ttk.Entry(self.custom_frame, textvariable=self.custom_height_var, width=8).pack(
            side=tk.LEFT, padx=(5, 0)
        )
        
        # 预估文件大小
        ttk.Label(self.custom_frame, text="预估大小:").pack(side=tk.LEFT, padx=(20, 5))
        self.size_estimate_label = ttk.Label(self.custom_frame, text="--")
        self.size_estimate_label.pack(side=tk.LEFT)
        
        # 绑定事件
        self.resolution_combo.bind('<<ComboboxSelected>>', self.on_resolution_change)
        self.custom_width_var.trace('w', self.update_size_estimate)
        self.custom_height_var.trace('w', self.update_size_estimate)
        self.fps_var.trace('w', self.update_size_estimate)
        self.quality_var.trace('w', self.update_size_estimate)
        # 绑定时间变化事件，用于重新计算推荐
        self.start_time_var.trace('w', self.on_time_change)
        self.end_time_var.trace('w', self.on_time_change)
        
        self.custom_frame.pack_forget()  # 初始隐藏自定义分辨率
        row += 1
        
        # 输出路径设置
        output_frame = ttk.Frame(main_frame)
        output_frame.grid(row=row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
        output_frame.columnconfigure(1, weight=1)
        
        ttk.Label(output_frame, text="输出路径:").grid(row=0, column=0, sticky=tk.W)
        self.output_path_var = tk.StringVar(value=str(self.output_dir))
        ttk.Entry(output_frame, textvariable=self.output_path_var).grid(
            row=0, column=1, sticky=(tk.W, tk.E), padx=(5, 5)
        )
        ttk.Button(output_frame, text="浏览", command=self.browse_output_path).grid(
            row=0, column=2
        )
        row += 1
        
        # 控制按钮
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=row, column=0, columnspan=3, pady=20)
        
        self.convert_button = ttk.Button(
            button_frame, text="开始转换", command=self.start_conversion
        )
        self.convert_button.pack(side=tk.LEFT, padx=(0, 10))
        
        self.stop_button = ttk.Button(
            button_frame, text="停止转换", command=self.stop_conversion, state=tk.DISABLED
        )
        self.stop_button.pack(side=tk.LEFT)
        row += 1
        
        # 进度条
        self.progress_var = tk.StringVar(value="就绪")
        ttk.Label(main_frame, textvariable=self.progress_var).grid(
            row=row, column=0, columnspan=3, pady=5
        )
        row += 1
        
        self.progress_bar = ttk.Progressbar(
            main_frame, mode='indeterminate'
        )
        self.progress_bar.grid(row=row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)
        
        # 初始化输入方式显示
        self.on_input_method_change()
    
    def on_input_method_change(self):
        """输入方式改变时的回调"""
        if self.input_method_var.get() == "url":
            self.url_frame.grid(row=1, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)
            self.file_frame.grid_remove()
            self.is_local_file = False
        else:
            self.file_frame.grid(row=1, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)
            self.url_frame.grid_remove()
            self.is_local_file = True
    
    def select_local_file(self):
        """选择本地视频文件"""
        file_types = [
            ("视频文件", "*.mp4 *.avi *.mkv *.mov *.wmv *.flv *.webm *.m4v"),
            ("所有文件", "*.*")
        ]
        
        file_path = filedialog.askopenfilename(
            title="选择视频文件",
            filetypes=file_types
        )
        
        if file_path:
            self.file_path_var.set(file_path)
            self.local_file_path = file_path
            # 自动获取本地文件信息
            self.get_video_info()
    
    def on_resolution_change(self, event):
        """分辨率选择改变事件"""
        if self.resolution_var.get() == "自定义":
            self.custom_frame.pack(fill=tk.X, pady=5)
        else:
            self.custom_frame.pack_forget()
        
        # 更新压缩比例显示
        self.update_compression_info()
        self.update_size_estimate()
    
    def on_time_change(self, *args):
        """时间设置改变时的回调"""
        # 更新文件大小预估
        self.update_size_estimate()
        
        # 如果有视频信息，重新计算推荐（延迟执行避免频繁计算）
        if hasattr(self, 'video_info') and self.video_info:
            # 取消之前的延迟任务
            if hasattr(self, '_update_recommendations_job'):
                self.root.after_cancel(self._update_recommendations_job)
            
            # 延迟500ms执行更新，避免用户快速输入时频繁计算
            self._update_recommendations_job = self.root.after(500, self._delayed_update_recommendations)
    
    def _delayed_update_recommendations(self):
        """延迟更新推荐"""
        if hasattr(self, 'video_info') and self.video_info:
            formats = self.video_info.get('formats', [])
            best_video = None
            for fmt in formats:
                if fmt.get('vcodec') != 'none' and fmt.get('height'):
                    if not best_video or fmt.get('height', 0) > best_video.get('height', 0):
                        best_video = fmt
            
            if best_video and best_video.get('width') and best_video.get('height'):
                self._suggest_gif_resolution(best_video.get('width'), best_video.get('height'))
    
    def update_compression_info(self):
        """更新压缩比例信息"""
        if not self.video_info:
            self.compression_label.config(text="")
            return
        
        # 获取视频原始分辨率
        formats = self.video_info.get('formats', [])
        best_video = None
        for fmt in formats:
            if fmt.get('vcodec') != 'none' and fmt.get('height'):
                if not best_video or fmt.get('height', 0) > best_video.get('height', 0):
                    best_video = fmt
        
        if not best_video:
            return
        
        orig_width = best_video.get('width', 0)
        orig_height = best_video.get('height', 0)
        
        if orig_width == 0 or orig_height == 0:
            return
        
        # 获取目标分辨率
        if self.resolution_var.get() == "自定义":
            try:
                target_width = int(self.custom_width_var.get())
                target_height = int(self.custom_height_var.get())
            except ValueError:
                return
        else:
            try:
                target_width, target_height = map(int, self.resolution_var.get().split('x'))
            except ValueError:
                return
        
        # 计算压缩比例和限制检查
        compression_ratio = (target_width * target_height) / (orig_width * orig_height)
        compression_percent = compression_ratio * 100
        max_edge = max(target_width, target_height)
        
        # 构建显示文本
        if compression_percent < 100:
            text = f"压缩至 {compression_percent:.1f}%"
            color = "green"
        elif compression_percent == 100:
            text = "原始大小"
            color = "blue" 
        else:
            text = f"放大至 {compression_percent:.1f}%"
            color = "orange"
        
        # 修改限制警告逻辑 - 只提示不拒绝
        if max_edge > 500:
            text += f" (提示: 超出推荐边长)"
            color = "orange"  # 改为橙色提示而不是红色错误
        
        self.compression_label.config(text=text, foreground=color)
    
    def update_size_estimate(self, *args):
        """更新文件大小预估"""
        if not hasattr(self, 'video_info') or not self.video_info:
            self.size_estimate_label.config(text="--")
            return
        
        try:
            # 获取参数
            if self.resolution_var.get() == "自定义":
                width = int(self.custom_width_var.get())
                height = int(self.custom_height_var.get())
            else:
                width, height = map(int, self.resolution_var.get().split('x'))
            
            fps = int(self.fps_var.get())
            start_time = float(self.start_time_var.get())
            end_time = float(self.end_time_var.get())
            quality = self.quality_var.get()
            
            # 计算持续时间
            duration = end_time - start_time
            
            if duration <= 0:
                self.size_estimate_label.config(text="--")
                return
            
            # 根据质量获取颜色数
            quality_colors = {"高": 256, "中": 128, "低": 64}.get(quality, 128)
            
            # 使用改进的文件大小预估
            estimated_size_mb = self._estimate_gif_size(width, height, duration, fps, quality_colors)
            
            # 检查是否超过限制
            max_edge = max(width, height)
            
            size_text = f"{estimated_size_mb:.1f}MB"
            
            # 修改警告标识 - 只提示不拒绝
            warnings = []
            if estimated_size_mb > 4.0:
                warnings.append("大文件提示")
            if max_edge > 500:
                warnings.append("高分辨率")
            
            if warnings:
                size_text += f" ({', '.join(warnings)})"
                self.size_estimate_label.config(text=size_text, foreground="orange")  # 改为橙色提示
            else:
                size_text += " ✓"
                self.size_estimate_label.config(text=size_text, foreground="green")
            
        except (ValueError, ZeroDivisionError):
            self.size_estimate_label.config(text="--")
    
    def browse_output_path(self):
        """浏览输出路径"""
        path = filedialog.askdirectory(initialdir=self.output_path_var.get())
        if path:
            self.output_path_var.set(path)
    
    def get_video_info(self):
        """获取视频信息"""
        if self.is_local_file:
            # 处理本地文件
            if not self.local_file_path or not os.path.exists(self.local_file_path):
                messagebox.showerror("错误", "请选择有效的本地视频文件")
                return
            file_path = self.local_file_path
        else:
            # 处理在线链接
            url = self.url_var.get().strip()
            if not url:
                messagebox.showerror("错误", "请输入视频链接")
                return
            
            if not self.is_bilibili_url(url):
                messagebox.showerror("错误", "请输入有效的bilibili视频链接")
                return
            file_path = url
        
        self.progress_var.set("获取视频信息中...")
        self.progress_bar.start()
        
        # 在新线程中获取视频信息
        threading.Thread(target=self._get_video_info_thread, args=(file_path,), daemon=True).start()
    
    def is_bilibili_url(self, url):
        """检查是否为bilibili链接"""
        bilibili_patterns = [
            r'bilibili\.com/video/[ABab][Vv]\w+',
            r'b23\.tv/\w+',
            r'bilibili\.com/video/BV\w+',
            r'bilibili\.com/video/av\d+'
        ]
        return any(re.search(pattern, url) for pattern in bilibili_patterns)
    
    def _get_video_info_thread(self, source):
        """获取视频信息线程"""
        try:
            if self.is_local_file:
                # 处理本地文件
                self._get_local_video_info(source)
            else:
                # 处理在线链接
                import yt_dlp
                
                ydl_opts = {
                    'quiet': False,
                    'no_warnings': False,
                    # 添加用户代理
                    'http_headers': {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                    }
                }
                
                print(f"正在获取视频信息: {source}")
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(source, download=False)
                    self.video_info = info
                    
                    print(f"视频标题: {info.get('title', '未知')}")
                    print(f"视频时长: {info.get('duration', 0)}秒")
                    
                    # 显示可用格式信息
                    formats = info.get('formats', [])
                    print(f"可用格式数量: {len(formats)}")
                    
                    for i, fmt in enumerate(formats[:5]):  # 只显示前5个格式
                        print(f"格式{i+1}: {fmt.get('format_id', 'unknown')} - "
                              f"{fmt.get('ext', 'unknown')} - "
                              f"{fmt.get('width', '?')}x{fmt.get('height', '?')} - "
                              f"{fmt.get('vcodec', 'unknown')}")
                    
                    # 更新GUI
                    self.root.after(0, self._update_video_info, info)
                
        except Exception as e:
            error_msg = str(e)
            print(f"获取视频信息失败: {error_msg}")
            self.logger.error(f"获取视频信息失败: {error_msg}")
            self.root.after(0, lambda msg=error_msg: messagebox.showerror("错误", f"获取视频信息失败: {msg}"))
        finally:
            self.root.after(0, self._stop_progress)
    
    def _get_local_video_info(self, file_path):
        """获取本地视频信息"""
        try:
            if CV2_AVAILABLE:
                # 使用OpenCV获取视频信息
                cap = cv2.VideoCapture(file_path)
                if not cap.isOpened():
                    raise Exception(f"无法打开视频文件: {file_path}")
                
                # 获取基本信息
                width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                fps = cap.get(cv2.CAP_PROP_FPS)
                frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                duration = frame_count / fps if fps > 0 else 0
                
                cap.release()
                
                # 构建伪造的info结构以兼容现有代码
                file_name = Path(file_path).stem
                self.video_info = {
                    'title': file_name,
                    'duration': duration,
                    'uploader': '本地文件',
                    'formats': [{
                        'width': width,
                        'height': height,
                        'fps': fps,
                        'vcodec': 'unknown',
                        'ext': Path(file_path).suffix[1:]
                    }]
                }
                
                print(f"本地视频信息: {width}x{height}, {duration:.1f}秒")
                
            else:
                # 如果没有OpenCV，使用ffprobe
                try:
                    cmd = ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', '-show_streams', file_path]
                    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
                    probe_data = json.loads(result.stdout)
                    
                    # 找到视频流
                    video_stream = None
                    for stream in probe_data.get('streams', []):
                        if stream.get('codec_type') == 'video':
                            video_stream = stream
                            break
                    
                    if not video_stream:
                        raise Exception("未找到视频流")
                    
                    width = int(video_stream.get('width', 0))
                    height = int(video_stream.get('height', 0))
                    duration = float(probe_data.get('format', {}).get('duration', 0))
                    fps = eval(video_stream.get('r_frame_rate', '0/1'))
                    
                    file_name = Path(file_path).stem
                    self.video_info = {
                        'title': file_name,
                        'duration': duration,
                        'uploader': '本地文件',
                        'formats': [{
                            'width': width,
                            'height': height,
                            'fps': fps,
                            'vcodec': video_stream.get('codec_name', 'unknown'),
                            'ext': Path(file_path).suffix[1:]
                        }]
                    }
                    
                except (subprocess.CalledProcessError, FileNotFoundError, json.JSONDecodeError):
                    # 如果ffprobe也失败，使用基本信息
                    file_name = Path(file_path).stem
                    file_size = os.path.getsize(file_path) / (1024*1024)  # MB
                    
                    self.video_info = {
                        'title': file_name,
                        'duration': 60,  # 假设60秒
                        'uploader': '本地文件',
                        'formats': [{
                            'width': 1920,  # 假设1080p
                            'height': 1080,
                            'fps': 25,
                            'vcodec': 'unknown',
                            'ext': Path(file_path).suffix[1:]
                        }]
                    }
                    
                    print(f"无法获取详细信息，使用默认值. 文件大小: {file_size:.1f}MB")
            
            # 更新GUI
            self.root.after(0, self._update_video_info, self.video_info)
            
        except Exception as e:
            error_msg = f"读取本地视频失败: {str(e)}"
            print(error_msg)
            self.root.after(0, lambda msg=error_msg: messagebox.showerror("错误", msg))
    
    def _update_video_info(self, info):
        """更新视频信息显示"""
        self.info_text.delete(1.0, tk.END)
        
        title = info.get('title', '未知')
        duration = info.get('duration', 0) or 0  # 确保duration不为None
        uploader = info.get('uploader', '未知')
        
        # 获取最佳视频格式信息
        formats = info.get('formats', [])
        best_video = None
        for fmt in formats:
            if fmt.get('vcodec') != 'none' and fmt.get('height'):
                if not best_video or fmt.get('height', 0) > best_video.get('height', 0):
                    best_video = fmt
        
        width = best_video.get('width', '未知') if best_video else '未知'
        height = best_video.get('height', '未知') if best_video else '未知'
        
        # 将duration转换为整数进行格式化
        duration_int = int(duration) if isinstance(duration, (int, float)) else 0
        minutes = duration_int // 60
        seconds = duration_int % 60
        
        info_text = f"标题: {title}\n"
        info_text += f"时长: {minutes}:{seconds:02d}\n"
        info_text += f"UP主: {uploader}\n"
        info_text += f"分辨率: {width}x{height}"
        
        self.info_text.insert(1.0, info_text)
        
        # 自动设置结束时间
        if duration and duration > 0:
            # 设置为视频长度和10秒中的较小值
            end_time = min(int(duration), 10)
            self.end_time_var.set(str(end_time))
        
        # 根据视频分辨率推荐GIF分辨率
        if best_video and best_video.get('width') and best_video.get('height'):
            self._suggest_gif_resolution(best_video.get('width'), best_video.get('height'))
        else:
            # 如果没有找到视频信息，显示默认提示
            self.recommend_text.config(state=tk.NORMAL)
            self.recommend_text.delete(1.0, tk.END)
            self.recommend_text.insert(1.0, "无法获取视频分辨率信息，请手动选择GIF分辨率")
            self.recommend_text.config(state=tk.DISABLED)
    
    def _suggest_gif_resolution(self, video_width, video_height):
        """根据视频分辨率智能推荐GIF分辨率 - 限制最大边500px，文件大小4MB"""
        if video_width == 0 or video_height == 0:
            return
        
        aspect_ratio = video_width / video_height
        
        # 获取当前时长设置用于文件大小计算
        try:
            duration = float(self.end_time_var.get()) - float(self.start_time_var.get())
            fps = int(self.fps_var.get())
        except (ValueError, AttributeError):
            duration = 10  # 默认值
            fps = 10
        
        if duration <= 0:
            duration = 10
        
        # 生成智能推荐选项
        recommendations = []
        
        # 1. 计算最大边为500的分辨率（最高质量选项）
        if video_width >= video_height:  # 横屏视频
            max_width = min(500, video_width)
            max_height = int(max_width / aspect_ratio)
        else:  # 竖屏视频
            max_height = min(500, video_height)
            max_width = int(max_height * aspect_ratio)
        
        # 确保尺寸为偶数
        max_width = max_width if max_width % 2 == 0 else max_width - 1
        max_height = max_height if max_height % 2 == 0 else max_height - 1
        
        # 2. 生成不同质量级别的推荐
        quality_levels = [
            {"name": "最佳质量", "scale": 1.0, "colors": 256, "quality_desc": "高"},
            {"name": "推荐", "scale": 0.8, "colors": 192, "quality_desc": "中"},
            {"name": "标准", "scale": 0.65, "colors": 128, "quality_desc": "中"},
            {"name": "小文件", "scale": 0.5, "colors": 96, "quality_desc": "低"}
        ]
        
        for level in quality_levels:
            # 计算该级别的分辨率
            width = int(max_width * level["scale"])
            height = int(max_height * level["scale"])
            
            # 确保尺寸为偶数且不小于最小值
            width = max(width if width % 2 == 0 else width - 1, 160)
            height = max(height if height % 2 == 0 else height - 1, 90)
            
            # 预估文件大小
            estimated_size_mb = self._estimate_gif_size(width, height, duration, fps, level["colors"])
            
            # 计算相对于原视频的压缩比
            compression = (width * height) / (video_width * video_height)
            
            recommendations.append({
                'width': width,
                'height': height,
                'name': level["name"],
                'desc': f'{width}x{height}',
                'size_mb': estimated_size_mb,
                'compression': compression,
                'colors': level["colors"],
                'quality': level["quality_desc"],
                'is_recommended': level["name"] == "推荐"
            })
        
        # 3. 去重并排序（按分辨率大小排序，最大的在前面）
        seen = set()
        unique_recommendations = []
        for rec in recommendations:
            key = (rec['width'], rec['height'])
            if key not in seen:
                seen.add(key)
                unique_recommendations.append(rec)
        
        # 按分辨率大小排序（从大到小）
        unique_recommendations.sort(key=lambda x: x['width'] * x['height'], reverse=True)
        
        # 更新UI
        self._update_recommendations_ui(unique_recommendations, video_width, video_height, duration)
        
        # 自动选择推荐的分辨率
        if unique_recommendations:
            # 优先选择标记为推荐的，否则选择第一个
            best_rec = None
            for rec in unique_recommendations:
                if rec.get('is_recommended'):
                    best_rec = rec
                    break
            
            if not best_rec:
                best_rec = unique_recommendations[0]
            
            self.resolution_var.set(f"{best_rec['width']}x{best_rec['height']}")
            self.custom_width_var.set(str(best_rec['width']))
            self.custom_height_var.set(str(best_rec['height']))
            
            # 根据推荐自动设置质量
            if best_rec['colors'] >= 200:
                self.quality_var.set("高")
            elif best_rec['colors'] >= 128:
                self.quality_var.set("中")
            else:
                self.quality_var.set("低")
        
        # 更新压缩信息
        self.update_compression_info()
        self.update_size_estimate()
    
    def _estimate_gif_size(self, width, height, duration, fps, colors):
        """预估GIF文件大小（MB）"""
        # GIF文件大小预估算法
        # 基于：分辨率 × 时长 × 帧率 × 颜色数量
        
        total_frames = duration * fps
        pixels_per_frame = width * height
        
        # 颜色数量影响系数
        color_factor = colors / 256
        
        # 基础字节数每像素（经验值）
        base_bytes_per_pixel = 0.8
        
        # GIF压缩效率（相邻帧的相似性）
        compression_efficiency = 0.4  # GIF压缩通常能减少60%的重复数据
        
        # 计算估算大小
        estimated_bytes = (pixels_per_frame * total_frames * base_bytes_per_pixel * 
                          color_factor * compression_efficiency)
        
        # 添加文件头和调色板开销
        overhead_bytes = 1024 + (colors * 3)  # 文件头 + 调色板
        
        total_bytes = estimated_bytes + overhead_bytes
        
        # 转换为MB
        size_mb = total_bytes / (1024 * 1024)
        
        return size_mb
    
    def _update_recommendations_ui(self, recommendations, orig_width, orig_height, duration=10):
        """更新推荐UI"""
        # 清除旧的推荐按钮
        for btn in self.recommend_buttons:
            btn.destroy()
        self.recommend_buttons.clear()
        
        # 更新推荐文本
        self.recommend_text.config(state=tk.NORMAL)
        self.recommend_text.delete(1.0, tk.END)
        
        max_edge = max(orig_width, orig_height)
        info_text = f"视频分辨率: {orig_width}x{orig_height} (最大边: {max_edge}px)\n"
        info_text += f"时长: {duration:.1f}秒 | 建议: 最大边≤500px, 文件≤4MB\n"
        
        if recommendations:
            info_text += f"为您推荐 {len(recommendations)} 个优化GIF配置:"
        else:
            info_text += "无法生成推荐配置，请手动调整参数"
        
        self.recommend_text.insert(1.0, info_text)
        self.recommend_text.config(state=tk.DISABLED)
        
        # 创建推荐按钮
        if not recommendations:
            return
            
        btn_frame = ttk.Frame(self.recommend_frame)
        btn_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(5, 0))
        
        # 计算按钮列数（最多4列）
        num_buttons = min(len(recommendations), 4)
        for i in range(num_buttons):
            btn_frame.columnconfigure(i, weight=1)
        
        for i, rec in enumerate(recommendations[:4]):  # 最多显示4个推荐
            # 构建按钮文本
            compression_percent = rec['compression'] * 100
            max_edge = max(rec['width'], rec['height'])
            
            btn_text = f"{rec['name']}\n"
            btn_text += f"{rec['desc']}\n"
            btn_text += f"≈{rec['size_mb']:.1f}MB"
            
            # 如果是推荐选项，添加标识
            if rec.get('is_recommended'):
                btn_text = f"⭐ {btn_text}"
            
            btn = ttk.Button(
                btn_frame, 
                text=btn_text,
                command=lambda r=rec: self._apply_recommendation(r),
                width=15
            )
            btn.grid(row=0, column=i, padx=(0, 5) if i < 3 else (0, 0), sticky=(tk.W, tk.E))
            self.recommend_buttons.append(btn)
        
        # 如果有更多推荐，显示提示
        if len(recommendations) > 4:
            info_label = ttk.Label(
                btn_frame, 
                text=f"(还有{len(recommendations)-4}个选项可在自定义中设置)",
                font=('TkDefaultFont', 8),
                foreground='gray'
            )
            info_label.grid(row=1, column=0, columnspan=4, pady=(5, 0))
    
    def _apply_recommendation(self, recommendation):
        """应用推荐的分辨率"""
        width = recommendation['width']
        height = recommendation['height']
        
        # 更新下拉框选项，如果不存在则添加
        current_values = list(self.resolution_combo['values'])
        new_resolution = f"{width}x{height}"
        
        if new_resolution not in current_values[:-1]:  # 排除"自定义"选项
            current_values.insert(-1, new_resolution)  # 在"自定义"前插入
            self.resolution_combo['values'] = current_values
        
        # 设置选中的分辨率
        self.resolution_var.set(new_resolution)
        self.custom_width_var.set(str(width))
        self.custom_height_var.set(str(height))
        
        # 根据推荐自动设置质量
        if 'quality' in recommendation and recommendation['quality'] in ['高', '中', '低']:
            self.quality_var.set(recommendation['quality'])
        elif 'colors' in recommendation:
            if recommendation['colors'] >= 200:
                self.quality_var.set("高")
            elif recommendation['colors'] >= 128:
                self.quality_var.set("中")
            else:
                self.quality_var.set("低")
        
        # 隐藏自定义框架
        self.custom_frame.pack_forget()
        
        # 更新相关信息
        self.update_compression_info()
        self.update_size_estimate()
        
        # 视觉反馈 - 临时高亮选中的按钮
        for btn in self.recommend_buttons:
            btn.config(state=tk.NORMAL)
        
        # 临时禁用选中的按钮表示已选择
        for btn in self.recommend_buttons:
            if f"{width}x{height}" in btn.cget('text'):
                original_text = btn.cget('text')
                btn.config(text=f"✓ 已选择\n{width}x{height}", state=tk.DISABLED)
                # 2秒后恢复原始文本
                self.root.after(2000, lambda b=btn, t=original_text: (
                    b.config(text=t, state=tk.NORMAL)
                ))
                break
    
    def _stop_progress(self):
        """停止进度条"""
        self.progress_bar.stop()
        self.progress_var.set("就绪")
    
    def _validate_conversion_params(self, width, height, fps, duration, estimated_size_mb):
        """验证转换参数是否合理 - 修改为只警告不拒绝"""
        warnings = []
        errors = []
        
        # 检查基础参数
        if width <= 0 or height <= 0:
            errors.append("分辨率必须大于0")
        
        if fps <= 0 or fps > 60:
            errors.append("帧率必须在1-60之间")
        
        if duration <= 0:
            errors.append("时长必须大于0")
        
        # 修改分辨率和文件大小检查 - 只警告不拒绝
        max_edge = max(width, height)
        if max_edge > 800:
            warnings.append(f"分辨率很大({max_edge}px)，转换可能较慢，建议使用推荐设置")
        elif max_edge > 500:
            warnings.append(f"分辨率较大({max_edge}px)，转换可能较慢")
        
        # 检查文件大小 - 只警告不拒绝
        if estimated_size_mb > 10:
            warnings.append(f"预估文件很大({estimated_size_mb:.1f}MB)，转换可能较慢且占用较多空间")
        elif estimated_size_mb > 4:
            warnings.append(f"预估文件较大({estimated_size_mb:.1f}MB)，转换可能较慢")
        
        # 检查帧数
        total_frames = duration * fps
        if total_frames > 500:
            warnings.append(f"总帧数较多({int(total_frames)}帧)，转换可能较慢")
        
        return warnings, errors
    
    def start_conversion(self):
        """开始转换"""
        if self.is_converting:
            return
        
        # 验证输入
        if not self.video_info:
            messagebox.showerror("错误", "请先获取视频信息")
            return
        
        try:
            start_time = float(self.start_time_var.get())
            end_time = float(self.end_time_var.get())
            fps = int(self.fps_var.get())
            
            if start_time >= end_time:
                messagebox.showerror("错误", "开始时间必须小于结束时间")
                return
            
            duration = end_time - start_time
            
        except ValueError:
            messagebox.showerror("错误", "请输入有效的数字")
            return
        
        # 获取分辨率
        if self.resolution_var.get() == "自定义":
            try:
                width = int(self.custom_width_var.get())
                height = int(self.custom_height_var.get())
            except ValueError:
                messagebox.showerror("错误", "请输入有效的自定义分辨率")
                return
        else:
            width, height = map(int, self.resolution_var.get().split('x'))
        
        # 预估文件大小用于参数验证
        quality_colors = {"高": 256, "中": 128, "低": 64}.get(self.quality_var.get(), 128)
        estimated_size_mb = self._estimate_gif_size(width, height, duration, fps, quality_colors)
        
        # 验证转换参数
        warnings, errors = self._validate_conversion_params(width, height, fps, duration, estimated_size_mb)
        
        if errors:
            messagebox.showerror("参数错误", "\n".join(errors))
            return
        
        if warnings:
            warning_msg = "\n".join(warnings) + "\n\n是否继续转换？"
            if not messagebox.askyesno("参数提示", warning_msg):
                return
        
        # 检查输出路径
        output_path = Path(self.output_path_var.get())
        if not output_path.exists():
            try:
                output_path.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                messagebox.showerror("错误", f"无法创建输出目录: {str(e)}")
                return
        
        # 开始转换
        self.is_converting = True
        self.convert_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        self.progress_bar.start()
        
        # 转换参数
        conversion_params = {
            'source': self.local_file_path if self.is_local_file else self.url_var.get(),
            'is_local_file': self.is_local_file,
            'start_time': start_time,
            'end_time': end_time,
            'width': width,
            'height': height,
            'fps': fps,
            'quality': self.quality_var.get(),
            'output_path': output_path,
            'remove_black_borders': self.auto_crop_var.get(),
            'remove_watermark': self.remove_watermark_var.get()
        }
        
        # 启动转换线程
        self.conversion_thread = threading.Thread(
            target=self._conversion_thread, 
            args=(conversion_params,), 
            daemon=True
        )
        self.conversion_thread.start()
    
    def stop_conversion(self):
        """停止转换"""
        self.is_converting = False
        self.progress_var.set("正在停止...")
    
    def _conversion_thread(self, params):
        """转换线程"""
        try:
            if params['is_local_file']:
                # 处理本地文件
                self.root.after(0, lambda: self.progress_var.set("处理本地视频中..."))
                temp_video = params['source']
            else:
                # 处理在线链接
                import yt_dlp
                
                self.root.after(0, lambda: self.progress_var.set("下载视频中..."))
                
                # 生成时间戳和文件名
                timestamp = int(time.time())
                
                # 临时视频文件 - 让yt-dlp决定扩展名
                temp_video_base = self.temp_dir / f"temp_video_{timestamp}"
                
                # 修复的下载策略 - 优先选择单一格式，避免需要合并的格式
                download_success = False
                temp_video = None
                
                # 优化的格式选择策略 - 避免需要合并的格式
                format_options = [
                    # 优先选择单一的完整格式，不需要合并
                    'best[ext=mp4][vcodec!=none][acodec!=none]',  # 优先mp4完整格式
                    'best[vcodec!=none][acodec!=none]',  # 任何完整格式
                    'best[ext=flv]',  # bilibili经常有flv格式
                    'worst[height>=360][vcodec!=none][acodec!=none]',  # 至少360p的完整格式
                    # 如果都没有，选择仅视频格式（无音频也可以转GIF）
                    'best[vcodec!=none]',  
                    'bestvideo[ext=mp4]',
                    'bestvideo',
                    # 最后的备选方案
                    'best'
                ]
                
                for format_selector in format_options:
                    ydl_opts = {
                        'outtmpl': str(temp_video_base) + '.%(ext)s',
                        'quiet': False,
                        'no_warnings': False,
                        'format': format_selector,
                        # 关键：不要尝试合并格式
                        'noplaylist': True,
                        'no_check_certificates': True,
                        'http_headers': {
                            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                        }
                    }
                    
                    try:
                        print(f"尝试格式: {format_selector}")
                        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                            ydl.download([params['source']])
                        
                        # 查找实际下载的文件
                        temp_video = None
                        for file in self.temp_dir.glob(f"temp_video_{timestamp}*"):
                            if file.is_file() and file.stat().st_size > 1024:  # 至少1KB
                                temp_video = file
                                print(f"找到下载文件: {temp_video}")
                                break
                        
                        if temp_video and temp_video.exists():
                            file_size = temp_video.stat().st_size / (1024*1024)
                            print(f"下载成功! 文件: {temp_video.name}, 大小: {file_size:.2f}MB")
                            download_success = True
                            break
                        else:
                            print(f"格式 '{format_selector}' 下载后未找到有效文件")
                        
                    except Exception as format_error:
                        print(f"格式 '{format_selector}' 下载失败: {str(format_error)}")
                        continue
                
                if not download_success or not temp_video:
                    error_msg = ("无法下载视频，可能的原因：\n"
                                "1. 网络连接问题\n"
                                "2. 视频链接无效或已失效\n"
                                "3. bilibili限制访问\n"
                                "4. 视频需要登录或有地区限制\n"
                                "\n建议：检查网络连接或尝试其他视频链接")
                    raise Exception(error_msg)
            
            if not self.is_converting:
                return
            
            self.root.after(0, lambda: self.progress_var.set("转换为GIF中..."))
            
            # 生成输出文件名
            timestamp = int(time.time())
            safe_title = re.sub(r'[^\w\s-]', '', self.video_info.get('title', 'video'))
            safe_title = re.sub(r'[-\s]+', '-', safe_title)
            output_file = params['output_path'] / f"{safe_title}_{timestamp}.gif"
            
            # 使用PIL方法转换GIF
            self._convert_with_pil(
                str(temp_video),
                str(output_file),
                params['start_time'],
                params['end_time'],
                params['width'],
                params['height'],
                params['fps'],
                params['quality'],
                params['remove_black_borders'],
                params['remove_watermark']
            )
            
            # 清理临时文件（只清理下载的文件，不清理本地文件）
            if not params['is_local_file'] and temp_video and temp_video.exists():
                try:
                    temp_video.unlink()
                except:
                    pass
            
            if self.is_converting:
                self.root.after(0, lambda: self._conversion_complete(output_file))
            
        except Exception as e:
            error_msg = str(e)
            self.logger.error(f"转换失败: {error_msg}")
            self.root.after(0, lambda msg=error_msg: self._conversion_error(msg))
        finally:
            self.root.after(0, self._conversion_finished)
    
    def _convert_with_pil(self, input_file, output_file, start_time, end_time, width, height, fps, quality, remove_black_borders, remove_watermark):
        """使用PIL进行转换（统一方法，包含智能裁切）"""
        try:
            from PIL import Image
            
            # 如果需要智能处理且OpenCV可用
            if (remove_black_borders or remove_watermark) and CV2_AVAILABLE:
                print("使用PIL智能裁切方法")
                self._convert_with_pil_smart_crop(input_file, output_file, start_time, end_time, width, height, fps, quality, remove_black_borders, remove_watermark)
            else:
                print("使用PIL标准方法")
                self._convert_with_pil_standard(input_file, output_file, start_time, end_time, width, height, fps, quality)
                
        except Exception as e:
            print(f"PIL转换失败: {str(e)}")
            raise
    
    def _convert_with_pil_smart_crop(self, input_file, output_file, start_time, end_time, width, height, fps, quality, remove_black_borders, remove_watermark):
        """使用PIL进行智能裁切转换"""
        try:
            from PIL import Image
            
            cap = cv2.VideoCapture(input_file)
            if not cap.isOpened():
                raise Exception(f"无法打开视频文件: {input_file}")
            
            # 设置开始位置
            cap.set(cv2.CAP_PROP_POS_MSEC, start_time * 1000)
            
            # 分析几帧确定裁切参数
            analysis_frames = []
            for i in range(3):
                ret, frame = cap.read()
                if ret:
                    analysis_frames.append(frame)
                    cap.set(cv2.CAP_PROP_POS_MSEC, (start_time + i * 2) * 1000)
            
            if not analysis_frames:
                raise Exception("无法读取分析帧")
            
            # 计算最优裁切参数
            crop_params_list = []
            for frame in analysis_frames:
                crop_top, crop_bottom, crop_left, crop_right = VideoProcessor.calculate_smart_crop(
                    frame, remove_black_borders, remove_watermark
                )
                crop_params_list.append((crop_top, crop_bottom, crop_left, crop_right))
            
            # 使用保守的裁切值
            if crop_params_list:
                final_crop_top = max(p[0] for p in crop_params_list)
                final_crop_bottom = max(p[1] for p in crop_params_list)
                final_crop_left = max(p[2] for p in crop_params_list)
                final_crop_right = max(p[3] for p in crop_params_list)
            else:
                final_crop_top = final_crop_bottom = final_crop_left = final_crop_right = 0
            
            # 重新设置到开始位置
            cap.set(cv2.CAP_PROP_POS_MSEC, start_time * 1000)
            
            frames = []
            frame_interval = 1.0 / fps
            current_time = start_time
            frame_count = 0
            max_frames = int((end_time - start_time) * fps)
            
            # 根据质量设置调色板大小
            quality_settings = {"高": 256, "中": 128, "低": 64}
            max_colors = quality_settings.get(quality, 128)
            
            while current_time < end_time and self.is_converting and frame_count < max_frames:
                ret, frame = cap.read()
                if not ret:
                    break
                
                # 应用智能裁切
                if any([final_crop_top, final_crop_bottom, final_crop_left, final_crop_right]):
                    h, w = frame.shape[:2]
                    crop_top = min(final_crop_top, h // 4)
                    crop_bottom = min(final_crop_bottom, h // 4)
                    crop_left = min(final_crop_left, w // 4)
                    crop_right = min(final_crop_right, w // 4)
                    
                    if crop_top + crop_bottom < h and crop_left + crop_right < w:
                        frame = frame[crop_top:h-crop_bottom, crop_left:w-crop_right]
                
                # 转换并调整大小
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                img = Image.fromarray(frame_rgb)
                img = img.resize((width, height), Image.Resampling.LANCZOS)
                
                if max_colors < 256:
                    img = img.quantize(colors=max_colors)
                
                frames.append(img)
                frame_count += 1
                
                # 跳到下一帧
                current_time += frame_interval
                cap.set(cv2.CAP_PROP_POS_MSEC, current_time * 1000)
                
                # 更新进度
                if frame_count % 10 == 0:
                    self.root.after(0, lambda fc=frame_count: self.progress_var.set(f"处理中... {fc}帧"))
            
            cap.release()
            
            if frames and self.is_converting:
                frames[0].save(
                    output_file,
                    save_all=True,
                    append_images=frames[1:],
                    duration=int(1000 / fps),
                    loop=0,
                    optimize=True
                )
                
                if not Path(output_file).exists() or Path(output_file).stat().st_size == 0:
                    raise Exception("PIL智能裁切保存失败")
            else:
                raise Exception("没有提取到有效帧")
                
        except Exception as e:
            print(f"PIL智能裁切失败: {str(e)}")
            raise
    
    def _convert_with_pil_standard(self, input_file, output_file, start_time, end_time, width, height, fps, quality):
        """使用PIL标准转换（备用方案）"""
        try:
            from PIL import Image
            import tempfile
            
            print(f"使用PIL标准转换: {width}x{height}, FPS:{fps}")
            
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_frames_pattern = os.path.join(temp_dir, "frame_%04d.png")
                
                # 尝试使用ffmpeg提取帧
                extract_cmd = [
                    'ffmpeg', '-y',
                    '-i', input_file,
                    '-ss', str(start_time),
                    '-t', str(end_time - start_time),
                    '-vf', f'fps={fps}',
                    '-frames:v', str(int((end_time - start_time) * fps * 1.2)),  # 限制最大帧数
                    temp_frames_pattern
                ]
                
                try:
                    result = subprocess.run(extract_cmd, check=True, capture_output=True, timeout=60)
                    print("使用ffmpeg提取帧成功")
                except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
                    # 如果ffmpeg失败，使用OpenCV
                    if CV2_AVAILABLE:
                        print("ffmpeg失败，使用OpenCV提取帧")
                        self._extract_frames_with_opencv(input_file, temp_dir, start_time, end_time, fps)
                    else:
                        raise Exception("无法提取视频帧，请确保安装了ffmpeg或opencv-python")
                
                # 读取帧
                frames = []
                frame_files = sorted([f for f in os.listdir(temp_dir) if f.startswith('frame_') and f.endswith('.png')])
                
                if not frame_files:
                    raise Exception("未能提取到视频帧")
                
                # 限制帧数防止内存问题
                if len(frame_files) > 200:
                    frame_files = frame_files[:200]
                    print(f"限制帧数到 {len(frame_files)} 帧以防止内存问题")
                
                quality_settings = {"高": 256, "中": 128, "低": 64}
                max_colors = quality_settings.get(quality, 128)
                
                for i, frame_file in enumerate(frame_files):
                    if not self.is_converting:
                        return
                    
                    frame_path = os.path.join(temp_dir, frame_file)
                    try:
                        with Image.open(frame_path) as img:
                            img = img.resize((width, height), Image.Resampling.LANCZOS)
                            if max_colors < 256:
                                img = img.quantize(colors=max_colors)
                            frames.append(img.copy())
                    except Exception as e:
                        print(f"跳过损坏帧: {frame_file}")
                        continue
                    
                    # 更新进度
                    if i % 10 == 0:
                        self.root.after(0, lambda fc=i: self.progress_var.set(f"处理帧 {fc}/{len(frame_files)}"))
                
                if frames and self.is_converting:
                    frames[0].save(
                        output_file,
                        save_all=True,
                        append_images=frames[1:],
                        duration=int(1000 / fps),
                        loop=0,
                        optimize=True
                    )
                    
                    if not os.path.exists(output_file) or os.path.getsize(output_file) == 0:
                        raise Exception("PIL标准转换保存失败")
                else:
                    raise Exception("没有提取到有效帧或转换被取消")
                    
        except Exception as e:
            print(f"PIL标准转换失败: {str(e)}")
            raise
    
    def _extract_frames_with_opencv(self, input_file, temp_dir, start_time, end_time, fps):
        """使用OpenCV提取帧"""
        if not CV2_AVAILABLE:
            raise Exception("OpenCV不可用")
        
        cap = cv2.VideoCapture(input_file)
        if not cap.isOpened():
            raise Exception(f"无法打开视频文件: {input_file}")
        
        # 设置开始位置
        cap.set(cv2.CAP_PROP_POS_MSEC, start_time * 1000)
        
        frame_interval = 1.0 / fps
        current_time = start_time
        frame_count = 0
        
        while current_time < end_time and self.is_converting:
            ret, frame = cap.read()
            if not ret:
                break
            
            # 保存帧
            frame_path = os.path.join(temp_dir, f"frame_{frame_count:04d}.png")
            cv2.imwrite(frame_path, frame)
            frame_count += 1
            
            # 跳到下一帧
            current_time += frame_interval
            cap.set(cv2.CAP_PROP_POS_MSEC, current_time * 1000)
        
        cap.release()
        
        if frame_count == 0:
            raise Exception("OpenCV未能提取到任何帧")
    
    def _conversion_complete(self, output_file):
        """转换完成"""
        self.progress_var.set("转换完成")
        messagebox.showinfo("完成", f"GIF已保存到: {output_file}")
        
        # 询问是否打开文件夹
        if messagebox.askyesno("打开文件夹", "是否打开输出文件夹？"):
            try:
                if os.name == 'nt':  # Windows
                    os.startfile(output_file.parent)
                elif os.name == 'posix':  # macOS和Linux
                    subprocess.run(['open' if sys.platform == 'darwin' else 'xdg-open', output_file.parent])
            except Exception as e:
                print(f"无法打开文件夹: {e}")
    
    def _conversion_error(self, error_msg):
        """转换错误"""
        self.progress_var.set("转换失败")
        messagebox.showerror("错误", f"转换失败: {error_msg}")
    
    def _conversion_finished(self):
        """转换结束清理"""
        self.is_converting = False
        self.convert_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        self.progress_bar.stop()
        if not self.progress_var.get().startswith("转换"):
            self.progress_var.set("就绪")

def main():
    """主函数"""
    print("启动 Bilibili视频转GIF工具By:樱流...")
    
    # 设置环境变量解决Windows编码问题
    if os.name == 'nt':
        os.environ['PYTHONIOENCODING'] = 'utf-8'
        try:
            import locale
            locale.setlocale(locale.LC_ALL, 'C.UTF-8')
        except:
            try:
                locale.setlocale(locale.LC_ALL, '.UTF8')
            except:
                os.environ['LC_ALL'] = 'C.UTF-8'
    
    # 检查并安装依赖库
    try:
        LibraryInstaller.check_and_install_packages()
    except Exception as e:
        print(f"库检查过程中出现错误: {e}")
        print("尝试继续运行...")
    
    # 创建GUI
    root = tk.Tk()
    app = BilibiliToGifConverter(root)
    
    try:
        root.mainloop()
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()