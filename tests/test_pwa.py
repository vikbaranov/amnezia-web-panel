import unittest

from pwa import build_webmanifest


class BuildWebmanifestTest(unittest.TestCase):
    def test_returns_required_pwa_fields(self):
        manifest = build_webmanifest({'title': 'My Panel', 'subtitle': 'VPN'})

        self.assertEqual(manifest['name'], 'My Panel')
        self.assertEqual(manifest['short_name'], 'My Panel')
        self.assertEqual(manifest['start_url'], '/')
        self.assertEqual(manifest['scope'], '/')
        self.assertEqual(manifest['display'], 'standalone')
        self.assertEqual(manifest['background_color'], '#0a0a0f')
        self.assertEqual(manifest['theme_color'], '#0a0a0f')

    def test_icons_have_required_sizes_and_purposes(self):
        manifest = build_webmanifest({'title': 'My Panel'})
        sizes = {icon['sizes'] for icon in manifest['icons']}
        purposes = {icon['purpose'] for icon in manifest['icons']}

        self.assertIn('192x192', sizes)
        self.assertIn('512x512', sizes)
        self.assertIn('any', purposes)
        self.assertIn('maskable', purposes)

    def test_defaults_when_settings_empty(self):
        manifest = build_webmanifest({})

        self.assertEqual(manifest['name'], 'Amnezia Panel')
        self.assertTrue(manifest['description'])


if __name__ == '__main__':
    unittest.main()
