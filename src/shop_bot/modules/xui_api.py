import uuid
import json
import requests
from datetime import datetime, timedelta
import logging
from typing import Dict, Optional, Tuple
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class XUIClientAPI:
    def __init__(self, host_url: str, username: str, password: str):
        self.host_url = host_url.rstrip('/')
        self.session = requests.Session()
        self.username = username
        self.password = password
        self.logged_in = False
        self.session.verify = False  # Отключаем проверку SSL
    
    def login(self) -> bool:
        try:
            login_url = f"{self.host_url}/login"
            response = self.session.post(login_url, data={
                "username": self.username,
                "password": self.password
            })
            if response.status_code == 200:
                result = response.json()
                if result.get('success'):
                    self.logged_in = True
                    logger.info(f"Logged in to {self.host_url}")
                    return True
            return False
        except Exception as e:
            logger.error(f"Login error: {e}")
            return False
    
    def get_inbound(self, inbound_id: int) -> Optional[Dict]:
        if not self.logged_in:
            return None
        try:
            url = f"{self.host_url}/panel/api/inbounds/get/{inbound_id}"
            response = self.session.get(url)
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    return data.get('obj')
            return None
        except Exception as e:
            logger.error(f"Failed to get inbound: {e}")
            return None
    
    def get_inbound_reality_params(self, inbound_id: int) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
        """Получает параметры Reality из инбаунда"""
        inbound = self.get_inbound(inbound_id)
        if not inbound:
            return None, None, None, None
        
        try:
            stream_settings = json.loads(inbound.get('streamSettings', '{}'))
            reality_settings = stream_settings.get('realitySettings', {})
            settings = reality_settings.get('settings', {})
            
            public_key = settings.get('publicKey')
            fingerprint = settings.get('fingerprint') or "chrome"
            server_names = reality_settings.get('serverNames', [])
            sni = server_names[0] if server_names else "www.yandex.ru"
            short_ids = reality_settings.get('shortIds', [])
            short_id = short_ids[0] if short_ids else "a2d716d5d68b61"
            
            logger.debug(f"Reality params from panel: pbk={public_key}, sni={sni}, sid={short_id}")
            return public_key, fingerprint, sni, short_id
        except Exception as e:
            logger.error(f"Failed to parse reality params: {e}")
            return None, None, None, None
    
    def add_client(self, inbound_id: int, client_data: Dict) -> bool:
        if not self.logged_in:
            return False
        try:
            url = f"{self.host_url}/panel/api/inbounds/addClient"
            payload = {"id": inbound_id, "settings": json.dumps({"clients": [client_data]})}
            response = self.session.post(url, json=payload)
            if response.status_code == 200:
                result = response.json()
                return result.get('success', False)
            return False
        except Exception as e:
            logger.error(f"Failed to add client: {e}")
            return False
    
    def update_client(self, inbound_id: int, client_uuid: str, email: str, new_expiry_ms: int) -> bool:
        if not self.logged_in:
            return False
        try:
            update_url = f"{self.host_url}/panel/api/inbounds/updateClient/{client_uuid}"
            payload = {
                "id": inbound_id,
                "settings": json.dumps({
                    "clients": [{
                        "id": client_uuid,
                        "email": email,
                        "enable": True,
                        "expiryTime": new_expiry_ms
                    }]
                })
            }
            response = self.session.post(update_url, json=payload)
            if response.status_code == 200:
                result = response.json()
                return result.get('success', False)
            return False
        except Exception as e:
            logger.error(f"Failed to update client: {e}")
            return False
    
    def get_client_by_email(self, inbound_id: int, email: str) -> Optional[Dict]:
        inbound = self.get_inbound(inbound_id)
        if not inbound:
            return None
        try:
            settings = json.loads(inbound.get('settings', '{}'))
            clients = settings.get('clients', [])
            for client in clients:
                if client.get('email') == email:
                    return client
            return None
        except Exception as e:
            logger.error(f"Failed to parse clients: {e}")
            return None
    
    def delete_client(self, inbound_id: int, client_uuid: str) -> bool:
        if not self.logged_in:
            return False
        try:
            url = f"{self.host_url}/panel/api/inbounds/{inbound_id}/delClient/{client_uuid}"
            response = self.session.post(url)
            if response.status_code == 200:
                result = response.json()
                return result.get('success', False)
            return False
        except Exception as e:
            logger.error(f"Failed to delete client: {e}")
            return False


def login_to_host(host_url: str, username: str, password: str, inbound_id: int):
    try:
        api = XUIClientAPI(host_url, username, password)
        if api.login():
            inbound = api.get_inbound(inbound_id)
            return api, inbound
        return None, None
    except Exception as e:
        logger.error(f"login_to_host error: {e}")
        return None, None


def get_subscription_link(user_uuid: str, host_url: str, host_name: str = None, sub_token: str = None, 
                          public_key: str = None, sni: str = None, short_id: str = None, 
                          fingerprint: str = "chrome", port: int = 443) -> str:
    """
    Возвращает VLESS-ссылку для подключения.
    Использует параметры из инбаунда, если они переданы.
    """
    try:
        parsed_url = urlparse(host_url)
        hostname = parsed_url.hostname or "localhost"
        
        # Используем переданные параметры или значения по умолчанию
        pbk = public_key or "w0sN_bKihovSlAzZogSjJjcYvnsNKLlc3ux28GbAZQo"
        s = sni or "www.yandex.ru"
        sid = short_id or "a2d716d5d68b61"
        fp = fingerprint or "chrome"
        
        connection_string = (
            f"vless://{user_uuid}@{hostname}:{port}"
            f"?type=tcp&encryption=none&security=reality"
            f"&pbk={pbk}&fp={fp}&sni={s}"
            f"&sid={sid}&spx=%2F&flow=xtls-rprx-vision"
            f"#{host_name or 'client'}"
        )
        
        return connection_string
        
    except Exception as e:
        logger.error(f"Ошибка формирования VLESS-ссылки: {e}", exc_info=True)
        return f"vless://{user_uuid}@{hostname}:443?type=tcp&security=reality&pbk={public_key}&sni={sni}&sid={short_id}#{host_name or 'client'}"


async def create_or_update_key_on_host(host_name: str, email: str, days_to_add: int = None, expiry_timestamp_ms: int = None) -> Dict:
    from shop_bot.data_manager.database import get_host
    
    host_data = get_host(host_name)
    if not host_data:
        logger.error(f"Host {host_name} not found")
        return None
    
    api = XUIClientAPI(host_data['host_url'], host_data['host_username'], host_data['host_pass'])
    if not api.login():
        logger.error(f"Failed to login to {host_name}")
        return None
    
    inbound_id = host_data['host_inbound_id']
    
    # Получаем параметры Reality из инбаунда
    public_key, fingerprint, sni, short_id = api.get_inbound_reality_params(inbound_id)
    logger.info(f"Reality params for {host_name}: pbk={public_key}, sni={sni}, sid={short_id}")
    
    existing_client = api.get_client_by_email(inbound_id, email)
    current_time_ms = int(datetime.now().timestamp() * 1000)
    
    if expiry_timestamp_ms is not None:
        new_expiry_ms = int(expiry_timestamp_ms)
    else:
        if days_to_add is None:
            return None
        if existing_client and existing_client.get('expiryTime', 0) > current_time_ms:
            new_expiry_dt = datetime.fromtimestamp(existing_client['expiryTime'] / 1000) + timedelta(days=days_to_add)
        else:
            new_expiry_dt = datetime.now() + timedelta(days=days_to_add)
        new_expiry_ms = int(new_expiry_dt.timestamp() * 1000)
    
    client_uuid = None
    success = False
    
    if existing_client:
        client_uuid = existing_client.get('id')
        success = api.update_client(inbound_id, client_uuid, email, new_expiry_ms)
    else:
        client_uuid = str(uuid.uuid4())
        import secrets
        client_data = {
            "id": client_uuid,
            "email": email,
            "enable": True,
            "flow": "xtls-rprx-vision",
            "expiryTime": new_expiry_ms,
            "limitIp": 0,
            "totalGB": 0,
            "subId": secrets.token_hex(12)
        }
        success = api.add_client(inbound_id, client_data)
    
    if not success:
        logger.error(f"Failed to update/create client {email}")
        return None
    
    # Формируем VLESS-ссылку с параметрами из панели
    connection_string = get_subscription_link(
        client_uuid, 
        host_data['host_url'], 
        host_name,
        public_key=public_key,
        sni=sni,
        short_id=short_id,
        fingerprint=fingerprint,
        port=443
    )
    
    return {
        "client_uuid": client_uuid,
        "email": email,
        "expiry_timestamp_ms": new_expiry_ms,
        "connection_string": connection_string,
        "host_name": host_name
    }


async def get_key_details_from_host(key_data: dict) -> dict:
    host_name = key_data.get('host_name')
    if not host_name:
        return None
    
    from shop_bot.data_manager.database import get_host
    
    host_db_data = get_host(host_name)
    if not host_db_data:
        return None
    
    user_uuid = key_data.get('xui_client_uuid')
    if not user_uuid:
        return None
    
    # Получаем параметры Reality из панели
    api = XUIClientAPI(host_db_data['host_url'], host_db_data['host_username'], host_db_data['host_pass'])
    if api.login():
        inbound_id = host_db_data['host_inbound_id']
        public_key, fingerprint, sni, short_id = api.get_inbound_reality_params(inbound_id)
    else:
        public_key, fingerprint, sni, short_id = None, None, None, None
    
    connection_string = get_subscription_link(
        user_uuid, 
        host_db_data['host_url'], 
        host_name,
        public_key=public_key,
        sni=sni,
        short_id=short_id,
        fingerprint=fingerprint,
        port=443
    )
    
    return {"connection_string": connection_string}


async def delete_client_on_host(host_name: str, client_email: str) -> bool:
    from shop_bot.data_manager.database import get_host, get_key_by_email
    
    host_data = get_host(host_name)
    if not host_data:
        return False
    
    api = XUIClientAPI(host_data['host_url'], host_data['host_username'], host_data['host_pass'])
    if not api.login():
        return False
    
    client_to_delete = get_key_by_email(client_email)
    if client_to_delete:
        return api.delete_client(host_data['host_inbound_id'], client_to_delete['xui_client_uuid'])
    return True