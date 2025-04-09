from typing import Any
import requests
import logging

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

# 配置日志记录
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class UnsplashProvider(ToolProvider):
    """Unsplash API工具提供者
    提供Unsplash图片搜索功能的接口
    """
    
    API_BASE_URL = "https://api.unsplash.com"
    
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        """验证Unsplash API凭证
        
        Args:
            credentials: 包含access_key的凭证字典
            
        Raises:
            ToolProviderCredentialValidationError: 当凭证验证失败时抛出
        """
        try:
            access_key = credentials.get('access_key')
            if not access_key:
                raise ValueError("Unsplash Access Key不能为空")
            
            # 使用简单的请求测试API密钥
            headers = {
                'Authorization': f'Client-ID {access_key}'
            }
            
            # 测试API密钥是否有效
            test_url = f"{self.API_BASE_URL}/photos"
            logger.info(f"Testing Unsplash API with a request to {test_url}")
            
            response = requests.get(test_url, headers=headers)
            
            if response.status_code == 401:
                raise ValueError("无效的Unsplash Access Key")
            elif response.status_code == 403:
                raise ValueError("Unsplash API权限被拒绝，请检查您的应用状态")
            elif response.status_code == 429:
                raise ValueError("超出Unsplash API请求限制，请稍后再试")
            elif response.status_code != 200:
                raise ValueError(f"API请求失败，状态码: {response.status_code}，错误: {response.text}")
                
            logger.info("Unsplash API凭证验证成功")
            
        except requests.RequestException as e:
            error_msg = f"API请求异常: {str(e)}"
            logger.error(error_msg)
            raise ToolProviderCredentialValidationError(error_msg)
        except Exception as e:
            error_msg = f"凭证验证失败: {str(e)}"
            logger.error(error_msg)
            raise ToolProviderCredentialValidationError(error_msg)
