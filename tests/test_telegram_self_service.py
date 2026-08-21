import asyncio
import copy
import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import telegram_bot as tg_bot


def base_data():
    return {
        'settings': {
            'self_service': {
                'enabled': True,
                'web_enabled': True,
                'telegram_enabled': True,
                'max_connections_per_user': 5,
                'rate_limit_count': 3,
                'rate_limit_window_seconds': 60,
                'allowed_protocols': ['awg', 'awg2'],
            }
        },
        'users': [
            {'id': 'user-1', 'username': 'alice', 'enabled': True, 'telegramId': '111'},
            {'id': 'user-2', 'username': 'bob', 'enabled': True, 'telegramId': '222', 'role': 'admin'},
        ],
        'servers': [
            {
                'name': 'Server 1',
                'host': 'vpn.example.test',
                'self_service_enabled': True,
                'protocols': {'awg': {'port': '55424'}, 'awg2': {'port': '55425'}, 'xray': {'port': '443'}},
            },
            {
                'name': 'Server 2',
                'host': 'vpn2.example.test',
                'self_service_enabled': False,
                'protocols': {'awg': {'port': '55424'}},
            },
        ],
        'user_connections': [],
    }


class TestUserCreateCallback(unittest.IsolatedAsyncioTestCase):
    """Test user_create shows self-service servers."""

    def setUp(self):
        tg_bot._callback_refs.clear()
        tg_bot._pending_inputs.clear()
        self.data = base_data()
        self.load_data = lambda: self.data
        self.api = AsyncMock()
        self.api.send_message = AsyncMock()
        self.api.edit_message = AsyncMock()
        self.api.answer_callback = AsyncMock()

    async def test_user_create_shows_servers_for_eligible_user(self):
        msg = _callback_update(chat_id=111, from_id=111, data_str='user_create')
        await _dispatch_callback(self.api, msg, self.load_data)
        self.api.edit_message.assert_called()
        call_kwargs = self.api.edit_message.call_args
        reply_markup = call_kwargs[1].get('reply_markup', {})
        keyboard_text = json.dumps(reply_markup)
        self.assertIn('Server 1', keyboard_text)
        # Verify there are callback buttons (resolved refs)
        self.assertIn('callback_data', keyboard_text)

    async def test_user_create_shows_no_servers_message_when_self_service_disabled(self):
        self.data['settings']['self_service']['enabled'] = False
        msg = _callback_update(chat_id=111, from_id=111, data_str='user_create')
        await _dispatch_callback(self.api, msg, self.load_data)
        text = self.api.edit_message.call_args[0][2]
        self.assertIn('administrator', text.lower())

    async def test_user_create_shows_no_servers_message_when_user_not_linked(self):
        msg = _callback_update(chat_id=999, from_id=999, data_str='user_create')
        await _dispatch_callback(self.api, msg, self.load_data)
        self.api.answer_callback.assert_called()
        text = self.api.edit_message.call_args[0][2]
        self.assertIn('denied', text.lower())


class TestUserCreateServerCallback(unittest.IsolatedAsyncioTestCase):
    """Test user_create_server shows protocol options."""

    def setUp(self):
        tg_bot._callback_refs.clear()
        tg_bot._pending_inputs.clear()
        self.data = base_data()
        self.load_data = lambda: self.data
        self.api = AsyncMock()
        self.api.send_message = AsyncMock()
        self.api.edit_message = AsyncMock()
        self.api.answer_callback = AsyncMock()

    async def test_user_create_server_shows_protocols(self):
        payload = {'sid': 0}
        ref_key = tg_bot._ref('user_create_server', payload)
        msg = _callback_update(chat_id=111, from_id=111, data_str=ref_key)
        await _dispatch_callback(self.api, msg, self.load_data)
        call_kwargs = self.api.edit_message.call_args
        reply_markup = call_kwargs[1].get('reply_markup', {})
        keyboard_text = json.dumps(reply_markup)
        self.assertIn('AmneziaWG', keyboard_text)
        self.assertIn('AmneziaWG 2.0', keyboard_text)


class TestUserCreateCancel(unittest.IsolatedAsyncioTestCase):
    """Test user_create_cancel returns to connections list."""

    def setUp(self):
        tg_bot._callback_refs.clear()
        tg_bot._pending_inputs.clear()
        self.data = base_data()
        self.load_data = lambda: self.data
        self.api = AsyncMock()
        self.api.send_message = AsyncMock()
        self.api.edit_message = AsyncMock()
        self.api.answer_callback = AsyncMock()

    async def test_user_create_cancel_returns_to_connections(self):
        msg = _callback_update(chat_id=111, from_id=111, data_str='user_create_cancel')
        await _dispatch_callback(self.api, msg, self.load_data)
        self.api.send_message.assert_called()
        text = self.api.send_message.call_args[0][1]
        self.assertIn('connection', text.lower())


class TestUserSelfServiceCreation(unittest.IsolatedAsyncioTestCase):
    """Test full creation flow via ConnectionService."""

    def setUp(self):
        tg_bot._callback_refs.clear()
        tg_bot._pending_inputs.clear()
        self.data = base_data()
        self.load_data = lambda: self.data
        self.api = AsyncMock()
        self.api.send_message = AsyncMock(return_value={"result": {"message_id": 100}})
        self.api.edit_message = AsyncMock()
        self.api.answer_callback = AsyncMock()
        self.api.send_document = AsyncMock()
        self.api.call = AsyncMock()

        self.mock_service = MagicMock()
        self.mock_service.create_user_connection = AsyncMock(return_value={
            'status': 'success',
            'config': '[Interface]\nPrivateKey = abc',
            'vpn_link': 'vpn://abc',
            'connection': {'id': 'conn-1', 'name': 'MyPhone'},
        })

    async def test_creation_succeeds_for_eligible_user(self):
        payload = {'sid': 0, 'proto': 'awg', 'name': 'MyPhone'}
        ref_key = tg_bot._ref('user_add_client', payload)
        msg = _callback_update(chat_id=111, from_id=111, data_str=ref_key)
        await _dispatch_callback_with_service(self.api, msg, self.load_data, self.mock_service)
        self.mock_service.create_user_connection.assert_called_once()
        self.api.send_message.assert_called()

    async def test_creation_fails_for_non_eligible_user(self):
        payload = {'sid': 0, 'proto': 'awg', 'name': 'MyPhone'}
        ref_key = tg_bot._ref('user_add_client', payload)
        msg = _callback_update(chat_id=999, from_id=999, data_str=ref_key)
        await _dispatch_callback_with_service(self.api, msg, self.load_data, self.mock_service)
        self.mock_service.create_user_connection.assert_not_called()
        self.api.answer_callback.assert_called()
        text = self.api.edit_message.call_args[0][2]
        self.assertIn('denied', text.lower())

    async def test_creation_fails_when_self_service_disabled(self):
        self.data['settings']['self_service']['enabled'] = False
        payload = {'sid': 0, 'proto': 'awg', 'name': 'MyPhone'}
        ref_key = tg_bot._ref('user_add_client', payload)
        msg = _callback_update(chat_id=111, from_id=111, data_str=ref_key)
        await _dispatch_callback_with_service(self.api, msg, self.load_data, self.mock_service)
        self.mock_service.create_user_connection.assert_not_called()


class TestUserAddClientNameInputState(unittest.IsolatedAsyncioTestCase):
    """Test user_add_client_name pending input resolves user fresh."""

    def setUp(self):
        tg_bot._callback_refs.clear()
        tg_bot._pending_inputs.clear()
        self.data = base_data()
        self.load_data = lambda: self.data
        self.api = AsyncMock()
        self.api.send_message = AsyncMock(return_value={"result": {"message_id": 100}})
        self.api.edit_message = AsyncMock()
        self.api.answer_callback = AsyncMock()
        self.api.send_document = AsyncMock()
        self.api.call = AsyncMock()

        self.mock_service = MagicMock()
        self.mock_service.create_user_connection = AsyncMock(return_value={
            'status': 'success',
            'config': '[Interface]\nPrivateKey = abc',
            'vpn_link': 'vpn://abc',
            'connection': {'id': 'conn-1', 'name': 'MyPhone'},
        })

    async def test_input_state_resolves_user_fresh(self):
        tg_bot._pending_inputs['111'] = {
            'kind': 'user_add_client_name',
            'sid': 0,
            'proto': 'awg',
            'ts': 0,
        }
        # _handle_pending_input expects the raw message dict (not wrapped in 'message' key)
        msg = {'chat': {'id': 111}, 'from': {'id': 111, 'first_name': 'Test'}, 'text': 'MyPhone'}
        handled = await tg_bot._handle_pending_input(
            self.api, msg, self.load_data, None, lambda c: 'vpn://x', self.mock_service
        )
        self.assertTrue(handled)
        self.mock_service.create_user_connection.assert_called_once()
        call_args = self.mock_service.create_user_connection.call_args
        self.assertEqual(call_args[0][0], 'user-1')

    async def test_input_state_rejects_unlinked_user(self):
        tg_bot._pending_inputs['999'] = {
            'kind': 'user_add_client_name',
            'sid': 0,
            'proto': 'awg',
            'ts': 0,
        }
        msg = {'chat': {'id': 999}, 'from': {'id': 999, 'first_name': 'Test'}, 'text': 'MyPhone'}
        handled = await tg_bot._handle_pending_input(
            self.api, msg, self.load_data, None, lambda c: 'vpn://x', self.mock_service
        )
        self.assertTrue(handled)
        self.mock_service.create_user_connection.assert_not_called()
        self.api.send_message.assert_called()
        text = self.api.send_message.call_args[0][1]
        self.assertIn('denied', text.lower())


def _callback_update(chat_id, from_id, data_str):
    return {
        'callback_query': {
            'id': f'cb-{from_id}',
            'from': {'id': from_id},
            'message': {'chat': {'id': chat_id}, 'message_id': 42},
            'data': data_str,
        }
    }


def _text_message(chat_id, from_id, text):
    return {
        'message': {
            'chat': {'id': chat_id},
            'from': {'id': from_id, 'first_name': 'Test'},
            'text': text,
        }
    }


async def _dispatch_callback(api, update, load_data):
    generate_vpn_link_fn = lambda c: f'vpn://{c}'
    await tg_bot._dispatch(api, update, load_data, generate_vpn_link_fn, None)


async def _dispatch_callback_with_service(api, update, load_data, service):
    generate_vpn_link_fn = lambda c: f'vpn://{c}'
    await tg_bot._dispatch(api, update, load_data, generate_vpn_link_fn, None, self_service_svc=service)


if __name__ == '__main__':
    unittest.main()
