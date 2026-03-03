# -*- coding: utf-8 -*-
"""
颜色管理模块
处理xkcd颜色循环、deltaE计算等功能
"""

import random
from typing import List, Tuple, Dict
import matplotlib.colors as mcolors
from colorsys import rgb_to_hls
import numpy as np


def rgb_to_lab(rgb: Tuple[float, float, float]) -> Tuple[float, float, float]:
    """
    将RGB颜色转换为LAB颜色空间
    
    Args:
        rgb: RGB元组，值范围0-1
        
    Returns:
        LAB颜色空间的元组
    """
    if not isinstance(rgb, (tuple, list)) or len(rgb) != 3:
        raise ValueError(f"Invalid RGB value: {rgb}")
    
    r, g, b = rgb
    
    # RGB to XYZ
    if r > 0.04045:
        r = pow((r + 0.055) / 1.055, 2.4)
    else:
        r = r / 12.92
    
    if g > 0.04045:
        g = pow((g + 0.055) / 1.055, 2.4)
    else:
        g = g / 12.92
    
    if b > 0.04045:
        b = pow((b + 0.055) / 1.055, 2.4)
    else:
        b = b / 12.92
    
    r = r * 100
    g = g * 100
    b = b * 100
    
    x = r * 0.4124 + g * 0.3576 + b * 0.1805
    y = r * 0.2126 + g * 0.7152 + b * 0.0722
    z = r * 0.0193 + g * 0.1192 + b * 0.9505
    
    # 使用D65光源
    x = x / 95.047
    y = y / 100.000
    z = z / 108.883
    
    # XYZ to LAB
    if x > 0.008856:
        x = pow(x, 1/3)
    else:
        x = (7.787 * x) + (16 / 116)
    
    if y > 0.008856:
        y = pow(y, 1/3)
    else:
        y = (7.787 * y) + (16 / 116)
    
    if z > 0.008856:
        z = pow(z, 1/3)
    else:
        z = (7.787 * z) + (16 / 116)
    
    L = (116 * y) - 16
    a = 500 * (x - y)
    b_lab = 200 * (y - z)
    
    return (L, a, b_lab)


def calculate_delta_e(lab1: Tuple[float, float, float], 
                      lab2: Tuple[float, float, float]) -> float:
    """
    计算两个颜色之间的deltaE（CIE76）
    
    Args:
        lab1: 第一个颜色的LAB值
        lab2: 第二个颜色的LAB值
        
    Returns:
        deltaE值
    """
    dL = lab1[0] - lab2[0]
    da = lab1[1] - lab2[1]
    db = lab1[2] - lab2[2]
    
    delta_e = np.sqrt(dL**2 + da**2 + db**2)
    return delta_e


def hex_to_rgb(hex_color: str) -> Tuple[float, float, float]:
    """
    将十六进制颜色转换为RGB（0-1范围）
    
    Args:
        hex_color: 十六进制颜色码
        
    Returns:
        RGB元组
    """
    hex_color = hex_color.lstrip('#')
    r = int(hex_color[0:2], 16) / 255.0
    g = int(hex_color[2:4], 16) / 255.0
    b = int(hex_color[4:6], 16) / 255.0
    return (r, g, b)


def get_xkcd_colors_list() -> List[str]:
    """
    获取所有xkcd颜色的列表
    
    Returns:
        xkcd颜色的十六进制码列表
    """
    try:
        xkcd_colors = mcolors.XKCD_COLORS
        return list(xkcd_colors.keys())
    except AttributeError:
        # 如果XKCD_COLORS不可用，使用CSS颜色作为备用
        return list(mcolors.CSS4_COLORS.keys())


def generate_xkcd_color_sequence(random_seed: int | None = None, 
                                  delta_e_min: float = 20.0,
                                  num_colors: int = 50) -> List[str]:
    """
    使用随机种子生成满足最小deltaE要求的xkcd颜色序列
    排除和白色过于接近的颜色（deltaE < delta_e_min）以及亮度过高的颜色（L* >= 80）
    
    Args:
        random_seed: 随机种子，用于可重复的随机数生成
        delta_e_min: 颜色之间的最小deltaE值（默认为20）
        num_colors: 要生成的颜色数（默认为50）
        
    Returns:
        满足要求的颜色十六进制码列表
    """
    if random_seed is not None:
        random.seed(int(random_seed))
    
    # 白色在LAB空间中的值
    white_rgb = (1.0, 1.0, 1.0)
    white_lab = rgb_to_lab(white_rgb)
    
    # 获取所有可用的xkcd颜色
    all_colors = get_xkcd_colors_list()
    
    # 随机打乱顺序
    shuffled_colors = all_colors.copy()
    random.shuffle(shuffled_colors)
    
    # 选择的颜色列表
    selected_colors = []
    used_indices = set()
    
    # 首先尝试从打乱后的颜色中选择前num_colors个颜色
    candidate_indices = list(range(min(num_colors * 5, len(shuffled_colors))))  # 候选范围更大
    
    for i in candidate_indices:
        if len(selected_colors) >= num_colors:
            break
        
        if i in used_indices:
            continue
        
        current_color = shuffled_colors[i]
        
        try:
            # 获取当前颜色的RGB值
            if current_color in mcolors.XKCD_COLORS:
                hex_color = mcolors.XKCD_COLORS[current_color]
            else:
                hex_color = mcolors.CSS4_COLORS.get(current_color, '#000000')
            
            # 如果hex_color是元组，转换为十六进制字符串
            if isinstance(hex_color, tuple):
                hex_color = mcolors.rgb2hex(hex_color)
            
            rgb = hex_to_rgb(hex_color)
            current_lab = rgb_to_lab(rgb)
            
            # 检查亮度条件：L* < 80
            if current_lab[0] >= 80:
                continue
            
            # 检查与白色的deltaE距离：必须满足 > delta_e_min
            delta_e_to_white = calculate_delta_e(current_lab, white_lab)
            if delta_e_to_white < delta_e_min:
                continue
            
            # 检查是否满足与其他已选颜色的deltaE最小值要求
            valid = True
            for selected_color in selected_colors:
                if selected_color in mcolors.XKCD_COLORS:
                    selected_hex = mcolors.XKCD_COLORS[selected_color]
                else:
                    selected_hex = mcolors.CSS4_COLORS.get(selected_color, '#000000')
                
                # 如果selected_hex是元组，转换为十六进制字符串
                if isinstance(selected_hex, tuple):
                    selected_hex = mcolors.rgb2hex(selected_hex)
                
                selected_rgb = hex_to_rgb(selected_hex)
                selected_lab = rgb_to_lab(selected_rgb)
                
                delta_e = calculate_delta_e(current_lab, selected_lab)
                if delta_e < delta_e_min:
                    valid = False
                    break
            
            if valid:
                selected_colors.append(current_color)
                used_indices.add(i)
        except (ValueError, KeyError, AttributeError):
            # 跳过无效颜色
            continue
    
    # 如果未能选择足够的颜色，使用默认颜色补充
    if len(selected_colors) < num_colors:
        # 尝试从剩余颜色中选择
        remaining_indices = [i for i in range(len(shuffled_colors)) if i not in used_indices]
        for i in remaining_indices:
            if len(selected_colors) >= num_colors:
                break
            try:
                current_color = shuffled_colors[i]
                if current_color not in selected_colors:
                    # 检查亮度条件
                    if current_color in mcolors.XKCD_COLORS:
                        hex_color = mcolors.XKCD_COLORS[current_color]
                    else:
                        hex_color = mcolors.CSS4_COLORS.get(current_color, '#000000')
                    
                    if isinstance(hex_color, tuple):
                        hex_color = mcolors.rgb2hex(hex_color)
                    
                    rgb = hex_to_rgb(hex_color)
                    current_lab = rgb_to_lab(rgb)
                    
                    # 只有亮度满足要求才加入
                    if current_lab[0] < 80:
                        selected_colors.append(current_color)
            except (ValueError, KeyError, AttributeError):
                continue
    
    # 如果仍然不足，使用默认颜色
    if len(selected_colors) < num_colors:
        default_colors = list(mcolors.TABLEAU_COLORS.keys())[:num_colors - len(selected_colors)]
        selected_colors.extend(default_colors)
    
    # 转换为十六进制码
    hex_colors = []
    for color_name in selected_colors[:num_colors]:
        try:
            if color_name in mcolors.XKCD_COLORS:
                hex_val = mcolors.XKCD_COLORS[color_name]
            else:
                hex_val = mcolors.CSS4_COLORS.get(color_name, '#000000')
            
            # 转换为十六进制字符串
            if isinstance(hex_val, tuple):
                hex_val = mcolors.rgb2hex(hex_val)
            
            hex_colors.append(hex_val)
        except:
            hex_colors.append('#000000')
    
    return hex_colors


def get_default_colors(num_colors: int = 50) -> List[str]:
    """
    获取默认颜色序列
    
    Args:
        num_colors: 需要的颜色数
        
    Returns:
        颜色十六进制码列表
    """
    try:
        import matplotlib.pyplot as plt
        if num_colors <= 10:
            cmap = plt.cm.get_cmap('tab10')
            colors = [mcolors.rgb2hex(cmap(i)) for i in range(num_colors)]
        elif num_colors <= 20:
            cmap = plt.cm.get_cmap('tab20')
            colors = [mcolors.rgb2hex(cmap(i)) for i in range(num_colors)]
        else:
            cmap = plt.cm.get_cmap('hsv')
            colors = [mcolors.rgb2hex(cmap(i / num_colors)) for i in range(num_colors)]
        return colors
    except:
        # 备用方案
        default_colors_list = list(mcolors.TABLEAU_COLORS.values())
        hex_colors = []
        for c in default_colors_list:
            if isinstance(c, tuple):
                hex_colors.append(mcolors.rgb2hex(c))
            else:
                hex_colors.append(c)
        
        if len(hex_colors) < num_colors:
            hex_colors = hex_colors * (num_colors // len(hex_colors) + 1)
        return hex_colors[:num_colors]
