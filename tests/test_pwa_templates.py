import pathlib
import re
import unittest


class PwaTemplateRegistrationTest(unittest.TestCase):
    def test_base_template_renders_bottom_nav(self):
        html = pathlib.Path('templates/base.html').read_text(encoding='utf-8')

        self.assertIn('class="bottom-nav"', html)
        self.assertIn('bottom-nav-link', html)
        self.assertIn('bottom-nav-icon', html)

    def test_css_styles_bottom_nav(self):
        css = pathlib.Path('static/css/style.css').read_text(encoding='utf-8')

        start = css.index('.bottom-nav {')
        end = css.index('}', start)
        block = css[start:end]
        self.assertIn('position: fixed', block)
        self.assertIn('display: none;', block)
        self.assertNotIn('!important', block)

        mobile = css.index('@media (max-width: 768px)', css.index('.bottom-nav'))
        self.assertIn('.bottom-nav', css[mobile:])
        self.assertIn('display: flex', css[mobile:])

    def test_css_contains_mobile_overflow_guards(self):
        css = pathlib.Path('static/css/style.css').read_text(encoding='utf-8')

        self.assertIn('#usersGrid', css)
        self.assertIn('.settings-grid', css)
        self.assertIn('.tunnel-actions', css)
        self.assertIn('#selfServiceControls', css)

    def test_users_template_uses_card_specific_layout_classes(self):
        html = pathlib.Path('templates/users.html').read_text(encoding='utf-8')

        self.assertIn('user-card', html)
        self.assertIn('user-card-avatar', html)
        self.assertIn('user-card-body', html)
        self.assertIn('user-card-header', html)
        self.assertIn('user-card-meta', html)
        self.assertIn('user-card-actions', html)

    def test_user_card_uses_explicit_avatar_body_actions_order(self):
        html = pathlib.Path('templates/users.html').read_text(encoding='utf-8')
        card_start = html.index('<div class="client-item user-card"')
        avatar = html.index('<div class="client-avatar user-card-avatar"', card_start)
        body_start = html.index('<div class="user-card-body">', avatar)
        card_template_end = html.index('`).join', body_start)
        actions = html.index('<div class="client-actions user-card-actions"', body_start)

        self.assertLess(avatar, body_start)
        self.assertLess(body_start, actions)
        self.assertLess(actions, card_template_end)

    def test_tunnel_buttons_wrap_text(self):
        css = pathlib.Path('static/css/style.css').read_text(encoding='utf-8')

        self.assertIn('.tunnel-actions .btn', css)
        self.assertIn('white-space: normal', css)
        self.assertIn('width: 100%', css)

    def test_templates_unregister_legacy_static_scope_worker(self):
        for template in ('templates/base.html', 'templates/login.html'):
            with self.subTest(template=template):
                html = pathlib.Path(template).read_text(encoding='utf-8')

                self.assertIn("navigator.serviceWorker.getRegistrations", html)
                self.assertIn("registration.scope.endsWith('/static/')", html)
                self.assertIn("registration.unregister()", html)
                self.assertIn("navigator.serviceWorker.register('/sw.js')", html)

    def test_server_template_does_not_show_aivpn_banner_above_connections(self):
        html = pathlib.Path('templates/server.html').read_text(encoding='utf-8')

        self.assertNotIn('<span class="promo-lock-badge">🔒 Coming soon</span>', html)
        self.assertNotIn('AI-driven protocol selection that picks the right tunnel for the moment.', html)

    def test_theme_toggle_update_targets_theme_button_by_id(self):
        """The PWA install control shares .theme-toggle but has no onclick.

        Using getAttribute('onclick').includes(...) throws TypeError in Firefox
        and leaves header icons in a broken state.
        """
        html = pathlib.Path('templates/base.html').read_text(encoding='utf-8')

        self.assertIn("btn.id === 'themeToggle'", html)
        self.assertNotIn("btn.getAttribute('onclick').includes('langModal')", html)

    def test_server_icon_uses_emoji_presentation(self):
        """U+1F5A5 without VS16 renders as a broken image in Firefox."""
        qualified = '\U0001F5A5\uFE0F'
        bare = re.compile(r'\U0001F5A5(?!\uFE0F)')
        for path in ('templates/server.html', 'templates/index.html'):
            with self.subTest(path=path):
                html = pathlib.Path(path).read_text(encoding='utf-8')
                self.assertIn(qualified, html)
                leftover = bare.findall(html)
                self.assertEqual(leftover, [], f'{path} still has desktop-computer without VS16')

    def test_text_default_emoji_use_variation_selector(self):
        """Text-default emoji render as a hex broken-image in Firefox without VS16.

        Unicode marks these as Emoji_Presentation=No; they need U+FE0F.
        """
        codepoints = (
            0x2139,   # INFORMATION SOURCE
            0x23F9,   # BLACK SQUARE FOR STOP
            0x2708,   # AIRPLANE
            0x2714,   # HEAVY CHECK MARK
            0x2716,   # HEAVY MULTIPLICATION X
            0x1F5A5,  # DESKTOP COMPUTER
            0x1F5D1,  # WASTEBASKET
            0x1F6E0,  # HAMMER AND WRENCH
            0x1F6E1,  # SHIELD
        )
        paths = list(pathlib.Path('templates').glob('*.html'))
        paths.extend([pathlib.Path('app.py'), pathlib.Path('telegram_bot.py')])
        for path in sorted(paths):
            text = path.read_text(encoding='utf-8')
            for cp in codepoints:
                leftover = re.findall(f'{chr(cp)}(?!\uFE0F)', text)
                self.assertEqual(
                    leftover, [],
                    f'{path} has U+{cp:04X} without VS16',
                )

    def test_pwa_install_button_has_firefox_fallback(self):
        """Chrome fires beforeinstallprompt; Firefox never does, so the 📲
        button stays display:none unless we offer a manual install path.
        """
        for path in ('templates/base.html', 'templates/login.html'):
            with self.subTest(path=path):
                html = pathlib.Path(path).read_text(encoding='utf-8')
                self.assertIn('beforeinstallprompt', html)
                self.assertIn('/Firefox\\//.test', html)
                self.assertIn("install_app_howto", html)

    def test_install_app_howto_exists_in_all_translations(self):
        for lang in ('en', 'ru', 'fr', 'zh', 'fa'):
            with self.subTest(lang=lang):
                data = pathlib.Path(f'translations/{lang}.json').read_text(encoding='utf-8')
                self.assertIn('"install_app_howto"', data)


if __name__ == '__main__':
    unittest.main()
