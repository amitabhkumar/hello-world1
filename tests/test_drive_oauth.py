from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock
from titan.drive_sync_oauth import deliver


class DeliveryTests(TestCase):
    def test_delivery_actions(self):
        for entries, action in [
            ([], "UPLOADED_NEW"),
            ([dict(id="a", name="x.csv", sha256Checksum="other")], "UPLOADED_REVISION"),
            ([dict(id="b", name="x.csv", sha256Checksum="hash")], "REUSED_DUPLICATE")
        ]:
            with self.subTest(action=action):
                drive = Mock()
                drive.candidates.return_value = entries
                drive.upload.return_value = "new"
                record = dict(folder_id="folder", sha256="hash")
                deliver(drive, Path("x.csv"), record)
                self.assertEqual(record["action"], action)
                drive.verify.assert_called_once_with(record["file_id"], "folder", "hash")
                self.assertEqual(record["readback_status"], "VERIFIED")
                self.assertEqual(drive.upload.called, action != "REUSED_DUPLICATE")
                if action == "UPLOADED_REVISION":
                    self.assertNotEqual(record["file_name"], "x.csv")
