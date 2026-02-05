# -*- coding: utf-8 -*-
"""
配置管理器
负责读取、保存、导入、导出config.json配置文件
"""

import json
import os
import copy
from pathlib import Path


# 默认配置
DEFAULT_CONFIG = {
    "plot": {
        "title": {
            "fontsize": 20,
            "bold": True
        },
        "xlabel": {
            "fontsize": 14,
            "bold": False
        },
        "ylabel": {
            "fontsize": 14,
            "bold": False
        },
        "xtick": {
            "fontsize": 10,
            "bold": False
        },
        "ytick": {
            "fontsize": 10,
            "bold": False
        },
        "legend": {
            "fontsize": 12,
            "bold": False
        },
        "text": {
            "fontsize": 16,
            "bold": True
        }
    }
}


class ConfigManager:
    """配置管理器类"""
    
    def __init__(self, config_path=None):
        """
        初始化配置管理器
        
        Args:
            config_path: config.json文件路径，默认为脚本同目录
        """
        if config_path is None:
            self.config_path = Path(__file__).parent / "config.json"
        else:
            self.config_path = Path(config_path)
        
        self.config = self._load_config()
    
    def _load_config(self):
        """从config.json加载配置，不存在则创建默认配置"""
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                # 合并默认配置和加载的配置（以加载的为准）
                return self._merge_config(DEFAULT_CONFIG, config)
            except Exception as e:
                print(f"加载配置文件失败: {e}，使用默认配置")
                return DEFAULT_CONFIG.copy()
        else:
            # 创建默认配置文件
            self.save_config(DEFAULT_CONFIG)
            return DEFAULT_CONFIG.copy()
    
    def _merge_config(self, default, loaded):
        """
        合并默认配置和加载的配置
        
        Args:
            default: 默认配置
            loaded: 加载的配置
            
        Returns:
            合并后的配置
        """
        result = copy.deepcopy(default)
        for key, value in loaded.items():
            if isinstance(value, dict) and key in result and isinstance(result[key], dict):
                result[key] = self._merge_config(result[key], value)
            else:
                result[key] = copy.deepcopy(value)
        return result
    
    def get_config(self):
        """获取完整配置"""
        return self.config
    
    def get_plot_config(self):
        """获取绘图配置"""
        return self.config.get('plot', {})
    
    def set_plot_config(self, plot_config):
        """设置绘图配置"""
        self.config['plot'] = plot_config
        self.save_config(self.config)
    
    def save_config(self, config=None):
        """
        保存配置到文件
        
        Args:
            config: 要保存的配置，如果为None则保存当前配置
        """
        if config is None:
            config = self.config
        
        try:
            # 确保目录存在
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"保存配置文件失败: {e}")
            return False
    
    def export_config(self, export_path):
        """
        导出配置到指定路径
        
        Args:
            export_path: 导出目标路径
            
        Returns:
            成功返回True，失败返回False
        """
        try:
            export_path = Path(export_path)
            export_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(export_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"导出配置失败: {e}")
            return False
    
    def import_config(self, import_path):
        """
        从指定路径导入配置，并保存到默认位置
        
        Args:
            import_path: 导入源路径
            
        Returns:
            成功返回True，失败返回False
        """
        try:
            import_path = Path(import_path)
            if not import_path.exists():
                print(f"配置文件不存在: {import_path}")
                return False
            
            with open(import_path, 'r', encoding='utf-8') as f:
                imported_config = json.load(f)
            
            # 合并导入的配置和默认配置
            self.config = self._merge_config(DEFAULT_CONFIG, imported_config)
            
            # 保存到默认位置
            self.save_config(self.config)
            return True
        except Exception as e:
            print(f"导入配置失败: {e}")
            return False
    
    def reset_config(self):
        """重置为默认配置"""
        self.config = DEFAULT_CONFIG.copy()
        self.save_config(self.config)
        return True
