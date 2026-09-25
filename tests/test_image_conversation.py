import base64
import hashlib
import hmac
import importlib.util
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


BOT_PATH = Path(__file__).resolve().parents[1] / 'line_bot.py'


def load_bot(name):
    spec = importlib.util.spec_from_file_location(name, BOT_PATH)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(os.environ, {
        'OPENAI_API_KEY': 'test-key',
        'LINE_BOT_API': 'test-token',
        'LINE_CHANNEL_SECRET_TOKEN': 'test-secret',
    }), patch('dotenv.load_dotenv'):
        spec.loader.exec_module(module)
    module.client = Mock()
    module.line_bot_api = Mock()
    module.messaging_api = Mock()
    module.slack = Mock()
    return module


class ImageConversationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        original_directory = os.getcwd()
        os.chdir(self.directory.name)
        self.addCleanup(os.chdir, original_directory)
        self.bot = load_bot('bot_worker_one')
        self.bot.line_bot_api.get_message_content.return_value = SimpleNamespace(
            content_type='image/png; charset=binary',
            iter_content=lambda: iter([b'png-', b'bytes']),
        )
        self.bot.client.responses.create.return_value = SimpleNamespace(
            id='response-image', output_text='画像の回答',
        )

    def send(self, bot, message_type, text=None, message_id='image-1', source=None):
        message = {'type': message_type, 'id': message_id}
        if text is not None:
            message['text'] = text
        body = json.dumps({'events': [{
            'type': 'message', 'timestamp': 0, 'replyToken': 'reply-token',
            'source': source or {'type': 'user', 'userId': 'user-1'},
            'message': message,
        }]})
        signature = base64.b64encode(hmac.new(
            b'test-secret', body.encode(), hashlib.sha256,
        ).digest()).decode()
        response = bot.app.test_client().post(
            '/', data=body, headers={'X-Line-Signature': signature},
        )
        self.assertEqual(response.status_code, 200)

    def test_image_question_and_followup_across_workers(self):
        self.bot.save_response_id('user-1', 'response-before')
        self.send(self.bot, 'image')
        self.bot.client.responses.create.assert_not_called()
        worker = load_bot('bot_worker_two')
        worker.client.responses.create.return_value = SimpleNamespace(
            id='response-image', output_text='画像の回答',
        )
        self.send(worker, 'text', 'この文字を翻訳して')
        call = worker.client.responses.create.call_args.kwargs
        self.assertEqual(call['previous_response_id'], 'response-before')
        self.assertEqual(call['context_management'], [
            {'type': 'compaction', 'compact_threshold': 30_000},
        ])
        self.assertEqual(call['input'][0]['content'], [
            {'type': 'input_text', 'text': 'この文字を翻訳して'},
            {'type': 'input_image', 'image_url': 'data:image/png;base64,' +
             base64.b64encode(b'png-bytes').decode()},
        ])
        self.assertIsNone(worker.get_pending_image('user-1'))
        self.send(self.bot, 'text', 'さらに詳しく')
        followup = self.bot.client.responses.create.call_args.kwargs
        self.assertEqual(followup['previous_response_id'], 'response-image')
        self.assertEqual(followup['input'], 'さらに詳しく')
        self.assertEqual(followup['context_management'], [
            {'type': 'compaction', 'compact_threshold': 30_000},
        ])

    def test_api_failure_preserves_image_and_history_for_retry(self):
        self.bot.save_response_id('user-1', 'response-before')
        self.send(self.bot, 'image')
        self.bot.client.responses.create.side_effect = RuntimeError('API unavailable')
        self.send(self.bot, 'text', '説明して')
        self.assertIsNotNone(self.bot.get_pending_image('user-1'))
        self.assertEqual(self.bot.get_response_id('user-1'), 'response-before')
        self.bot.client.responses.create.side_effect = None
        self.send(self.bot, 'text', 'もう一度説明して')
        self.assertIsNone(self.bot.get_pending_image('user-1'))

    def test_new_image_during_api_call_is_not_deleted(self):
        self.send(self.bot, 'image')

        def answer(**kwargs):
            self.send(self.bot, 'image', message_id='image-2')
            return SimpleNamespace(id='response-image', output_text='回答')

        self.bot.client.responses.create.side_effect = answer
        self.send(self.bot, 'text', '説明して')
        self.assertEqual(self.bot.get_pending_image('user-1')['message_id'], 'image-2')

    def test_pending_image_does_not_cross_chats_or_users(self):
        self.send(self.bot, 'image')
        for source in [
            {'type': 'user', 'userId': 'user-2'},
            {'type': 'group', 'groupId': 'group-1', 'userId': 'user-1'},
            {'type': 'room', 'roomId': 'room-1', 'userId': 'user-1'},
        ]:
            with self.subTest(source=source):
                self.send(self.bot, 'text', 'こんにちは', source=source)
                call = self.bot.client.responses.create.call_args.kwargs
                self.assertEqual(call['input'], 'こんにちは')
                self.assertIsNone(call['previous_response_id'])
        self.assertIsNotNone(self.bot.get_pending_image('user-1'))

    def test_empty_download_does_not_store_image(self):
        self.bot.line_bot_api.get_message_content.return_value.iter_content = lambda: iter([])
        self.send(self.bot, 'image')
        self.assertIsNone(self.bot.get_pending_image('user-1'))
        reply = self.bot.line_bot_api.reply_message.call_args.args[1].text
        self.assertIn('画像の受信に失敗', reply)

    def test_v3_reply_fallback_uses_v3_message(self):
        self.bot.line_bot_api.reply_message.side_effect = RuntimeError('reply failed')
        self.bot.reply_text('reply-token', '回答')
        reply = self.bot.messaging_api.reply_message.call_args.args[0]
        self.assertEqual(reply.messages[0].text, '回答')


if __name__ == '__main__':
    unittest.main()
