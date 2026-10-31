"""Public marketplace must not claim real identity verification without a provider."""
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

class PublicVerificationProofTests(unittest.TestCase):
    def test_backend_only_advertises_provider_verified_freelancers(self):
        server=(ROOT/"server.py").read_text("utf-8")
        directory=server[server.index("if method=='GET' and p=='/api/v1/freelancers':"):
                         server.index("if p=='/api/v1/freelancer/portfolio':")]
        self.assertIn("KYC_MODE=='adapter'",directory)
        self.assertIn("get('kyc_provider_reference')",directory)
        self.assertIn("x['provider_verified']=bool(",directory)
        self.assertIn("fp['provider_verified']=bool(",directory)
        self.assertIn("if verified=='1':a=[x for x in a if x.get('provider_verified') is True]",directory)
        self.assertIn("x['kyc_status']='pending'",directory)
        self.assertIn("fp['kyc_status']='pending'",directory)
        self.assertIn("x.pop('kyc_provider_reference',None)",directory)
        self.assertIn("fp.pop('kyc_provider_reference',None)",directory)
    def test_client_proposals_do_not_present_manual_identity_as_confirmed(self):
        server=(ROOT/"server.py").read_text("utf-8")
        start=server.index("if m and method=='GET':\n                u=self.require();")
        end=server.index("if p=='/api/v1/orders' and method=='POST':",start)
        proposals=server[start:end]
        self.assertIn("is_provider_verified=bool(KYC_MODE=='adapter'",proposals)
        self.assertIn("item['kyc_status']='pending'",proposals)
        self.assertIn("item.pop('kyc_provider_reference',None)",proposals)
    def test_public_badges_are_proven_and_new_freelancers_have_no_fake_100pct(self):
        page=(ROOT/"public/index.html").read_text("utf-8")
        public_profile=page[page.index("window.freelancerPublicModal=async function(fid)"):
                            page.index("window.inviteFreelancer=async function(fid)")]
        directory=page[page.index("window.renderFreelancerDirectory=async function()"):
                       page.index("const _renderClientHomeV420=renderClientHome")]
        self.assertIn("p.provider_verified===true",public_profile)
        self.assertIn("p.provider_verified===true",directory)
        self.assertIn("Number(p.completed_tasks||0)>0",public_profile)
        self.assertIn("Number(p.completed_tasks||0)>0",directory)
        self.assertIn("الهوية غير موثقة عبر مزود معتمد",public_profile)
        self.assertNotIn("p.on_time_rate||100",public_profile)
        self.assertNotIn("p.on_time_rate||100",directory)

if __name__=="__main__":unittest.main()
