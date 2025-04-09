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

class UnsplashTool(Tool):
    """Unsplash搜索工具
    提供Unsplash图片的搜索功能
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
        # 验证必填参数
        query = tool_parameters.get('query')
        if not query or not isinstance(query, str) or len(query.strip()) == 0:
            raise ValueError("Search query cannot be empty")
        
        # 验证页码和每页结果数
        per_page = tool_parameters.get('per_page', 10)
        if not isinstance(per_page, (int, float)) or per_page <= 0 or per_page > 30:
            raise ValueError("Results per page must be an integer between 1 and 30")
    
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
        """执行Unsplash图片搜索
        
        Args:
            tool_parameters: 搜索参数
            
        Yields:
            ToolInvokeMessage: 工具调用消息
        """
        try:
            # 验证参数
            self._validate_parameters(tool_parameters)
            
            # 获取参数
            query = tool_parameters.get('query')
            per_page = min(int(tool_parameters.get('per_page', 10)), 30)
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
            url = urljoin(self.API_BASE_URL, '/search/photos')
            params = {
                'query': query,
                'per_page': per_page,
                'page': 1
            }
            
            # 添加可选参数
            if orientation:
                params['orientation'] = orientation
            if color:
                params['color'] = color
            
            logger.info(f"Searching Unsplash with parameters: {params}")
            
            # 发送API请求
            start_time = time.time()
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
            request_time = time.time() - start_time
            
            logger.info(f"Unsplash API request completed in {request_time:.2f} seconds")
            
            # 处理响应数据
            results = data.get('results', [])
            total = data.get('total', 0)
            total_pages = data.get('total_pages', 0)
            
            # 创建文本消息，包含搜索结果摘要
            search_params = f"query='{query}'"
            if orientation:
                search_params += f", orientation='{orientation}'"
            if color:
                search_params += f", color='{color}'"
                
            if total > 0:
                summary_text = f"Found {total} photos for {search_params}. Showing {len(results)} results."
            else:
                summary_text = f"No photos found for {search_params}. Please try different keywords."
            
            # 只输出简短的摘要信息到文本
            yield self.create_text_message(summary_text)
            
            # 处理没有结果的情况
            if not results:
                yield self.create_json_message({
                    'photos': [],
                    'total': 0,
                    'total_pages': 0,
                    'error': None,
                    'search_parameters': {
                        'query': query,
                        'per_page': per_page,
                        'orientation': orientation,
                        'color': color
                    }
                })
                yield self.create_variable_message('photos', [])
                yield self.create_variable_message('total_results', 0)
                return
            
            # 构建返回结果
            photos = []
            photo_details = []
            
            for photo in results:
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
                        filename = f"unsplash_{photo_id}.jpg"
                        
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
            
            # 创建JSON消息，包含完整的搜索结果数据和照片详情
            result = {
                'photos': photos,
                'total': total,
                'total_pages': total_pages,
                'error': None,
                'search_parameters': {
                    'query': query,
                    'per_page': per_page,
                    'orientation': orientation,
                    'color': color
                },
                'photo_details': photo_details
            }
            yield self.create_json_message(result)
            
            # 创建变量消息，可在工作流中使用
            yield self.create_variable_message('photos', photos)
            yield self.create_variable_message('photo_details', photo_details)
            yield self.create_variable_message('total_results', total)
            
        except ValueError as e:
            # 参数验证错误
            error_message = f"Parameter error: {str(e)}"
            logger.error(error_message)
            yield self.create_text_message(error_message)
            yield self.create_json_message({'error': error_message})
            yield self.create_variable_message('photos', [])
            yield self.create_variable_message('total_results', 0)
            
        except requests.RequestException as e:
            # API请求错误
            error_message = f"Unsplash API request error: {str(e)}"
            logger.error(error_message)
            yield self.create_text_message(error_message)
            yield self.create_json_message({'error': error_message})
            yield self.create_variable_message('photos', [])
            yield self.create_variable_message('total_results', 0)
            
        except Exception as e:
            # 其他未预期的错误
            error_message = f"Error searching Unsplash: {str(e)}"
            logger.error(f"Unexpected error: {str(e)}", exc_info=True)
            yield self.create_text_message(error_message)
            yield self.create_json_message({'error': error_message})
            yield self.create_variable_message('photos', [])
            yield self.create_variable_message('total_results', 0)
