import pathlib
import unittest


class PwaTemplateRegistrationTest(unittest.TestCase):
    def test_base_template_does_not_render_bottom_nav(self):
        html = pathlib.Path('templates/base.html').read_text(encoding='utf-8')

        self.assertNotIn('bottom-nav', html)

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
