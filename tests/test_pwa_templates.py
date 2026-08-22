import pathlib
import unittest


class PwaTemplateRegistrationTest(unittest.TestCase):
    def test_base_template_does_not_render_bottom_nav(self):
        html = pathlib.Path('templates/base.html').read_text(encoding='utf-8')

        self.assertNotIn('bottom-nav', html)

    def test_css_hides_legacy_bottom_nav_markup(self):
        css = pathlib.Path('static/css/style.css').read_text(encoding='utf-8')

        self.assertIn('.bottom-nav', css)
        self.assertIn('display: none !important', css)

    def test_css_contains_mobile_overflow_guards(self):
        css = pathlib.Path('static/css/style.css').read_text(encoding='utf-8')

        self.assertIn('#usersGrid', css)
        self.assertIn('.settings-grid', css)
        self.assertIn('.tunnel-actions', css)
        self.assertIn('#selfServiceControls', css)

    def test_users_template_uses_card_specific_layout_classes(self):
        html = pathlib.Path('templates/users.html').read_text(encoding='utf-8')

        self.assertIn('user-card', html)
        self.assertIn('user-card-info', html)
        self.assertIn('user-card-body', html)
        self.assertIn('user-card-actions', html)

    def test_user_actions_are_inside_card_body(self):
        html = pathlib.Path('templates/users.html').read_text(encoding='utf-8')
        body_start = html.index('<div class="user-card-body">')
        card_template_end = html.index('`).join', body_start)
        body_fragment = html[body_start:card_template_end]

        self.assertIn('<div class="client-actions user-card-actions"', body_fragment)

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


if __name__ == '__main__':
    unittest.main()
