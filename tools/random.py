from collections.abc import Generator
from typing import Any, Optional
import requests
import logging
import time
from urllib.parse import urljoin
import io

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

# 配置日志记录
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class UnsplashRandomTool(Tool):
    """Unsplash随机图片工具
    提供从Unsplash获取随机图片的功能
    """
    
    API_BASE_URL = "https://api.unsplash.com"
    
    def get_credentials(self) -> dict[str, Any]:
        """获取Unsplash API凭证"""
        return self.runtime.credentials
    
    def _validate_parameters(self, tool_parameters: dict[str, Any]) -> None:
        """验证输入参数
        
        Args:
            tool_parameters: 工具参数
            
        Raises:
            ValueError: 当参数无效时抛出
        """
        # 验证数量参数
        count = tool_parameters.get('count', 1)
        if not isinstance(count, (int, float)) or count <= 0 or count > 30:
            raise ValueError("Photo count must be an integer between 1 and 30")
    
    def _build_photo_object(self, photo: dict) -> dict:
        """从API响应构建照片对象
        
        Args:
            photo: 原始照片数据
            
        Returns:
            结构化的照片对象
        """
        return {
            'id': photo.get('id'),
            'description': photo.get('description'),
            'alt_description': photo.get('alt_description'),
            'width': photo.get('width'),
            'height': photo.get('height'),
            'color': photo.get('color'),
            'likes': photo.get('likes'),
            'created_at': photo.get('created_at'),
            'updated_at': photo.get('updated_at'),
            'urls': {
                'raw': photo.get('urls', {}).get('raw'),
                'full': photo.get('urls', {}).get('full'),
                'regular': photo.get('urls', {}).get('regular'),
                'small': photo.get('urls', {}).get('small'),
                'thumb': photo.get('urls', {}).get('thumb'),
            },
            'user': {
                'id': photo.get('user', {}).get('id'),
                'name': photo.get('user', {}).get('name'),
                'username': photo.get('user', {}).get('username'),
                'portfolio_url': photo.get('user', {}).get('portfolio_url'),
                'profile_image': photo.get('user', {}).get('profile_image'),
            },
            'links': {
                'self': photo.get('links', {}).get('self'),
                'html': photo.get('links', {}).get('html'),
                'download': photo.get('links', {}).get('download'),
                'download_location': photo.get('links', {}).get('download_location'),
            }
        }
        
    def _download_image(self, url: str) -> bytes:
        """下载图片并返回二进制数据
        
        Args:
            url: 图片URL
            
        Returns:
            图片的二进制数据
        """
        try:
            logger.info(f"Downloading image: {url}")
            response = requests.get(url, stream=True)
            response.raise_for_status()
            return response.content
        except Exception as e:
            logger.error(f"Failed to download image: {str(e)}")
            raise
    
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        """执行Unsplash随机图片获取
        
        Args:
            tool_parameters: 工具参数
            
        Yields:
            ToolInvokeMessage: 工具调用消息
        """
        try:
            # 验证参数
            self._validate_parameters(tool_parameters)
            
            # 获取参数
            query = tool_parameters.get('query')
            count = min(int(tool_parameters.get('count', 1)), 30)
            orientation = tool_parameters.get('orientation')
            color = tool_parameters.get('color')
            
            # 获取凭证
            credentials = self.get_credentials()
            access_key = credentials.get('access_key')
            
            # 设置API请求头
            headers = {
                'Authorization': f'Client-ID {access_key}'
            }
            
            # 构建API请求URL和参数
            url = urljoin(self.API_BASE_URL, '/photos/random')
            params = {
                'count': count
            }
            
            # 添加可选参数
            if query:
                params['query'] = query
            if orientation:
                params['orientation'] = orientation
            if color:
                params['color'] = color
            
            logger.info(f"Fetching random photos from Unsplash with parameters: {params}")
            
            # 发送API请求
            start_time = time.time()
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            
            # 处理响应数据
            # 随机照片API返回单张照片时是对象，多张照片时是数组
            photos_data = response.json()
            if not isinstance(photos_data, list):
                photos_data = [photos_data]
                
            request_time = time.time() - start_time
            logger.info(f"Unsplash API request completed in {request_time:.2f} seconds")
            
            # 创建文本消息，包含获取结果摘要
            param_desc = []
            if query:
                param_desc.append(f"query='{query}'")
            if orientation:
                param_desc.append(f"orientation='{orientation}'")
            if color:
                param_desc.append(f"color='{color}'")
                
            param_str = ", ".join(param_desc) if param_desc else "no filters applied"
            summary_text = f"Retrieved {len(photos_data)} random photos ({param_str})"
            yield self.create_text_message(summary_text)
            
            # 处理没有结果的情况
            if not photos_data:
                yield self.create_json_message({
                    'photos': [],
                    'error': None,
                    'parameters': {
                        'query': query,
                        'count': count,
                        'orientation': orientation,
                        'color': color
                    }
                })
                yield self.create_variable_message('random_photos', [])
                return
            
            # 构建返回结果
            photos = []
            photo_details = []
            
            for photo in photos_data:
                # 构建照片对象
                photo_data = self._build_photo_object(photo)
                photos.append(photo_data)
                
                # 获取图片URL
                image_url = photo.get('urls', {}).get('regular')
                if image_url:
                    try:
                        # 下载图片
                        image_data = self._download_image(image_url)
                        
                        # 添加图片描述
                        description = (
                            photo.get('description') or 
                            photo.get('alt_description') or 
                            f"Photo by {photo.get('user', {}).get('name', 'Unknown')}"
                        )
                        
                        # 创建文件名
                        photo_id = photo.get('id', 'photo')
                        filename = f"unsplash_random_{photo_id}.jpg"
                        
                        # 使用blob_message发送图片数据
                        yield self.create_blob_message(
                            blob=image_data,
                            meta={
                                "mime_type": "image/jpeg",
                                "filename": filename,
                                "description": description
                            }
                        )
                        
                        # 将照片详细信息添加到列表中，而不是作为文本消息输出
                        user_name = photo.get('user', {}).get('name', 'Unknown')
                        user_link = photo.get('user', {}).get('links', {}).get('html', '')
                        photo_link = photo.get('links', {}).get('html', '')
                        dimensions = f"{photo.get('width', 'Unknown')}x{photo.get('height', 'Unknown')}"
                        
                        photo_detail = {
                            'id': photo.get('id'),
                            'description': description,
                            'dimensions': dimensions,
                            'author': user_name,
                            'photo_link': photo_link,
                            'user_link': user_link,
                            'license': "Unsplash License - https://unsplash.com/license"
                        }
                        
                        photo_details.append(photo_detail)
                        
                    except Exception as e:
                        logger.error(f"Error processing image: {str(e)}")
                        yield self.create_text_message(f"Failed to process image: {str(e)}")
            
            # 创建JSON消息，包含完整的结果数据和照片详情
            result = {
                'photos': photos,
                'error': None,
                'parameters': {
                    'query': query,
                    'count': count,
                    'orientation': orientation,
                    'color': color
                },
                'photo_details': photo_details
            }
            yield self.create_json_message(result)
            
            # 创建变量消息，可在工作流中使用
            yield self.create_variable_message('random_photos', photos)
            yield self.create_variable_message('photo_details', photo_details)
            
        except ValueError as e:
            # 参数验证错误
            error_message = f"Parameter error: {str(e)}"
            logger.error(error_message)
            yield self.create_text_message(error_message)
            yield self.create_json_message({'error': error_message})
            yield self.create_variable_message('random_photos', [])
            
        except requests.RequestException as e:
            # API请求错误
            error_message = f"Unsplash API request error: {str(e)}"
            logger.error(error_message)
            yield self.create_text_message(error_message)
            yield self.create_json_message({'error': error_message})
            yield self.create_variable_message('random_photos', [])
            
        except Exception as e:
            # 其他未预期的错误
            error_message = f"Error retrieving random photos: {str(e)}"
            logger.error(f"Unexpected error: {str(e)}", exc_info=True)
            yield self.create_text_message(error_message)
            yield self.create_json_message({'error': error_message})
            yield self.create_variable_message('random_photos', [])