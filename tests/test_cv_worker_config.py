import importlib
import os
import unittest


class CvWorkerConfigTests(unittest.TestCase):
    def test_camera_urls_defaults_to_webcam_when_not_configured(self):
        os.environ.pop("CAMERA_URLS", None)
        import cv_worker.config as config_module
        reloaded = importlib.reload(config_module)
        self.assertEqual(reloaded.CAMERA_URLS, ["0"])


if __name__ == "__main__":
    unittest.main()
