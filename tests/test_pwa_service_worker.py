import pathlib
import unittest


class ServiceWorkerCachingTest(unittest.TestCase):
    def test_static_assets_are_network_first_with_cache_fallback(self):
        sw = pathlib.Path('static/sw.js').read_text(encoding='utf-8')

        self.assertNotIn('caches.match(request).then((cached)', sw)
        self.assertIn("fetch(request).then((res) =>", sw)
        self.assertIn(".catch(() => caches.match(request))", sw)


if __name__ == '__main__':
    unittest.main()
