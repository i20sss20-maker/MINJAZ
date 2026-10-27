"""Smoke tests for public MINJAZ frontend routes; never touch user accounts."""
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from scripts import check_minjaz_launch_readiness as launch

ROOT="https://minjaz.example.com"

class FakeResponse:
    def __init__(self,body,content_type,status=200):
        self.body=body.encode("utf-8")
        self.headers={"Content-Type":content_type}
        self.status=status
    def __enter__(self):return self
    def __exit__(self,*exc):return False
    def read(self,n=1_000_000):return self.body[:n]

def valid_response(path):
    markers=launch.PUBLIC_UI_CONTRACT[path]
    mime="application/javascript; charset=utf-8" if path.endswith(".js") else "text/html; charset=utf-8"
    return FakeResponse(" <!doctype html>\n"+"\n".join(markers),mime)

class PublicUiSmokeTests(unittest.TestCase):
    def test_public_pages_load_with_correct_content_type_and_markers(self):
        visited=[]
        def fake_open(request,timeout=15):
            self.assertEqual(request.get_method(),"GET")
            self.assertEqual(timeout,15)
            path=request.full_url.removeprefix(ROOT)
            visited.append(path)
            return valid_response(path)
        with patch.object(launch.urllib.request,"urlopen",side_effect=fake_open):
            self.assertTrue(launch.check_public_ui(ROOT))
        self.assertEqual(set(visited),set(launch.PUBLIC_UI_CONTRACT))
        self.assertIn("/digital-services",visited)
        self.assertIn("/minjaz-account-registration-v1.js",visited)

    def test_missing_script_contract_blocks_readiness(self):
        def fake_open(request,timeout=15):
            path=request.full_url.removeprefix(ROOT)
            if path.endswith(".js"):
                return FakeResponse("const unrelated=true;","application/javascript")
            return valid_response(path)
        with patch.object(launch.urllib.request,"urlopen",side_effect=fake_open):
            with self.assertRaisesRegex(RuntimeError,"public interface contract missing"):
                launch.check_public_ui(ROOT)

    def test_html_instead_of_js_blocks_readiness(self):
        def fake_open(request,timeout=15):
            path=request.full_url.removeprefix(ROOT)
            if path.endswith(".js"):
                return FakeResponse(" ".join(launch.PUBLIC_UI_CONTRACT[path]),"text/html")
            return valid_response(path)
        with patch.object(launch.urllib.request,"urlopen",side_effect=fake_open):
            with self.assertRaisesRegex(RuntimeError,"missing or incorrect public page"):
                launch.check_public_ui(ROOT)

    def test_missing_store_page_blocks_readiness(self):
        def fake_open(request,timeout=15):
            path=request.full_url.removeprefix(ROOT)
            if path=="/digital-services":
                raise HTTPError(request.full_url,404,"not found",{},None)
            return valid_response(path)
        with patch.object(launch.urllib.request,"urlopen",side_effect=fake_open):
            with self.assertRaisesRegex(RuntimeError,"HTTP 404"):
                launch.check_public_ui(ROOT)

if __name__=="__main__":unittest.main()
