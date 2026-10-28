"""Fast isolated MINJAZ workspace must be navigable without legacy app load.

This is a preview-only UI; all reads/writes still use role-guarded existing APIs.
"""
import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER = (ROOT / "server.py").read_text(encoding="utf-8")
HTML = (ROOT / "public" / "workspace.html").read_text(encoding="utf-8")
JS = (ROOT / "public" / "workspace-v1.js").read_text(encoding="utf-8")
SIGNUP = (ROOT / "public" / "signup.html").read_text(encoding="utf-8")
STORE = (ROOT / "public" / "digital-services.html").read_text(encoding="utf-8")


class RoleWorkspaceTests(unittest.TestCase):
    def test_routes_are_preview_only_with_correct_mime(self):
        self.assertIn("p in ('/workspace','/workspace/')", SERVER)
        self.assertIn("p=='/workspace-v1.js'", SERVER)
        self.assertGreaterEqual(SERVER.count("if APP_ENV!='preview': return self.sendj(404,{'error':'not_found'})"), 3)
        self.assertIn("open(os.path.join(os.path.dirname(HTML_PATH),'workspace.html'),'rb')", SERVER)
        self.assertIn("open(os.path.join(os.path.dirname(HTML_PATH),'workspace-v1.js'),'rb')", SERVER)
        self.assertIn("self._headers(200,'application/javascript; charset=utf-8')", SERVER)

    def test_client_freelancer_admin_ux_present(self):
        for form in ("newTask", "offerForm", "nameForm", "freelancerProfile"):
            self.assertIn('id="'+form+'"', HTML)
        for endpoint in ("/api/v1/me", "/api/v1/tasks", "/api/v1/orders",
                         "/api/v1/notifications?limit=8", "/api/admin/summary",
                         "/api/v1/me/active-role", "/api/v1/freelancer/profile",
                         "/api/v1/legal/documents", "/api/v1/legal/accept",
                         "/api/v1/auth/logout"):
            self.assertIn(endpoint, JS)
        self.assertIn('credentials:"same-origin"', JS)
        self.assertIn("const esc=value=>", JS)

    def test_no_fake_money_or_unprotected_admin_access(self):
        # Do not offer mock payment actions, automatic legal acceptance,
        # or a client-side assertion of admin privilege.
        self.assertNotIn("/pay", JS)
        self.assertNotIn("payment_mode=mock", JS)
        self.assertNotIn("ADMIN_EMAIL", JS)
        self.assertIn('querySelectorAll(\'input[type="checkbox"]:checked\')', JS)
        self.assertIn('missing.some(x=>!checked.includes(x))', JS)
        self.assertIn('const result=await request("/api/admin/summary")', JS)

    def test_signup_and_store_use_fast_paths_not_broken_app_link(self):
        self.assertIn('href="/workspace"', SIGNUP)
        self.assertNotIn('href="/app"', SIGNUP)
        self.assertIn('window.location.assign(backToStore?"/digital-services":"/workspace")', SIGNUP)
        self.assertIn('href="/signup?auth=login&amp;next=digital-services"', STORE)
        self.assertIn("a.href='/signup?auth=login&next=digital-services'", STORE)
        self.assertNotIn('href="/?auth=login&amp;next=digital-services"', STORE)

    def test_website_assets_are_not_in_legacy_shell_or_service_worker(self):
        self.assertIn('src="/workspace-v1.js" defer', HTML)
        self.assertNotIn("public/index.html", HTML)
        self.assertIn("role", JS)
        self.assertIn("AbortController()", JS)
        self.assertIn("idempotency_key:", JS)
        self.assertIn("request(\"/api/v1/auth/logout\"", JS)

    def test_live_task_offer_order_workflows_are_wired_to_real_apis(self):
        for route in (
            '/api/v1/freelancer/proposals',
            '/api/v1/client/profile',
            '/api/v1/notifications/read-all',
            '/api/v1/tasks/"+id+"/close',
            '/api/v1/orders/"+id+"/messages',
            '/api/v1/orders/"+id+"/timeline',
        ):
            self.assertIn(route, JS)
        self.assertIn('request("/api/v1/orders",{method:"POST",data:{proposal_id:proposalId}})', JS)
        self.assertIn('method:"DELETE"', JS)
        self.assertIn('method:"PATCH"', JS)
        self.assertIn('idempotency_key:pendingMessageKey', JS)
        self.assertIn('idempotency_key:pendingTaskKey', JS)
        self.assertIn('data-action="open-order"', JS)
        self.assertIn('data-action="select-offer"', JS)
        self.assertIn('window.confirm', JS)
        self.assertIn("p.kyc_status===\"approved\"", JS)

    def test_new_forms_exist_and_every_js_dom_lookup_is_present(self):
        for key in ("proposalPanel", "proposalItems", "clientProfile", "clientCompany",
                    "clientBio", "clientCity", "clientSector", "markAllRead",
                    "orderDialog", "orderTitle", "orderInfo", "orderMessages",
                    "orderTimeline", "closeOrder", "refreshOrder", "messageBody", "messageForm"):
            self.assertIn('id="'+key+'"', HTML)
        js_ids=set(re.findall(r'\$\("([A-Za-z0-9_-]+)"\)', JS))
        html_ids=set(re.findall(r'id="([A-Za-z0-9_-]+)"', HTML))
        self.assertFalse(js_ids-html_ids, "Missing HTML elements: "+str(js_ids-html_ids))

    def test_real_order_is_pending_without_fake_payment(self):
        self.assertIn("لم يتم دفع أي مبلغ", JS)
        self.assertIn("لا ترسل أي مبالغ خارج المنصة", JS)
        self.assertIn("لن يُخصم أي مبلغ", JS)
        self.assertIn("الهوية غير موثقة", JS)
        self.assertIn("مزود الدفع", HTML)
        self.assertNotIn('request("/api/v1/orders/"+id+"/pay"', JS)
        self.assertNotIn("payment_mode=mock", JS)
        self.assertNotIn("مقبول ومدفوع", JS)

    def test_real_account_safety_and_support_workflows(self):
        for endpoint in (
            "/api/v1/account/sessions",
            "/api/v1/account/sessions/revoke-others",
            "/api/v1/account/sessions/"+'"+id',
            "/api/v1/privacy/export",
            "/api/v1/privacy/requests",
            "/api/v1/support/tickets",
            "/api/v1/safety/reports",
            "/api/v1/freelancer/portfolio",
            "/api/admin/operations",
            "/api/admin/support",
            "/api/admin/privacy",
            "/api/admin/safety/reports",
        ):
            self.assertIn(endpoint, JS)
        self.assertIn('idempotency_key:supportRequestKey', JS)
        self.assertIn('idempotency_key:privacyRequestKey', JS)
        self.assertIn('idempotency_key:portfolioRequestKey', JS)
        self.assertIn('idempotency_key:reportRequestKey', JS)
        self.assertIn('const payload=await request("/api/v1/privacy/export",{timeoutMs:45000})', JS)
        self.assertIn('URL.createObjectURL(blob)', JS)
        self.assertIn('window.confirm(', JS)
        self.assertIn('loadExtraPanels()', JS)
        self.assertNotIn('payment_mode=mock', JS)

    def test_account_panels_are_role_gated_and_present(self):
        for id_ in (
            "sessionsItems", "refreshSessions", "revokeOtherSessions",
            "downloadMyData", "portfolioPanel", "portfolioForm", "portfolioTitle",
            "portfolioDescription", "portfolioUrl", "portfolioItems", "kycStatus",
            "supportForm", "supportCategory", "supportSubject", "supportMessage",
            "supportItems", "safetyItems", "privacyForm", "privacyType",
            "privacyDetails", "privacyItems", "adminQueuesPanel", "adminStats",
            "adminQueues", "adminRefresh", "reportDialog", "reportForm",
            "reportTask", "reportOrder", "reportDetails", "reportCategory",
            "closeReport", "reportOrderButton", "adminTicketDialog", "adminTicketTitle",
            "adminTicketDetails", "adminTicketForm", "adminTicketId", "adminTicketStatus",
            "adminTicketReply", "closeAdminTicket"
        ):
            self.assertIn('id="'+id_+'"', HTML)
        self.assertIn('show("portfolioPanel",role==="freelancer")', JS)
        self.assertIn('show("adminQueuesPanel",role==="admin")', JS)
        self.assertIn('if(currentUser?.role!=="freelancer")return;', JS)
        self.assertIn('if(currentUser?.role!=="admin")return;', JS)
        self.assertIn('if(activeOrderId)openReportDialog({order_id:activeOrderId})', JS)
        self.assertNotIn("KYC_MODE=manual", JS)
        self.assertNotIn("role==='admin'", HTML)

    def test_server_restricts_account_data_and_admin_requests(self):
        # Every sensitive endpoint uses server-side identity and a SQL user ID,
        # not a client-supplied target ID.
        self.assertIn("if p=='/api/v1/account/sessions' and method=='GET':", SERVER)
        self.assertIn("if p=='/api/v1/support/tickets':", SERVER)
        self.assertIn("if p=='/api/v1/privacy/requests':", SERVER)
        self.assertIn("if p=='/api/v1/freelancer/portfolio':", SERVER)
        self.assertIn("if p.startswith('/api/admin'):", SERVER)
        self.assertIn("u=self.require('admin');", SERVER)
        self.assertIn("u=self.require('freelancer');", SERVER)
        self.assertIn("if p=='/api/admin/support' and method=='GET':", SERVER)
        self.assertIn("m=re.fullmatch(r'/api/admin/support/(\\d+)',p)", SERVER)
        self.assertIn('request("/api/admin/support/"+id,{method:"PATCH"', JS)
        self.assertIn('request("/api/v1/privacy/export",{timeoutMs:45000})', JS)
        self.assertIn("where user_id=%s", SERVER)

    def test_unpaid_order_cancellation_is_reviewed_not_fake_refunded(self):
        for dom_id in (
            "orderCancelSection", "orderCancelForm", "orderCancelInfo",
            "orderCancelReason", "orderCancelDetails", "adminCancellationDialog",
            "adminCancellationTitle", "adminCancellationDetails",
            "adminCancellationForm", "adminCancellationId",
            "adminCancellationStatus", "adminCancellationNote", "closeAdminCancellation"
        ):
            self.assertIn('id="'+dom_id+'"', HTML)
        for uri in (
            'request("/api/v1/orders/"+id+"/cancellation")',
            'request("/api/v1/orders/"+id+"/cancellation",{method:"POST"',
            'request("/api/admin/cancellations")',
            'request("/api/admin/cancellations/"+id,{method:"PATCH"'
        ):
            self.assertIn(uri, JS)
        self.assertIn('idempotency_key:orderCancelKey', JS)
        self.assertIn('if(status==="approved"&&req.payment_status==="paid")', JS)
        self.assertIn('option.disabled=req.payment_status==="paid"', JS)
        self.assertIn('لم يتغير وضع الدفع', JS)
        self.assertIn("لا يمكن اعتماد إلغاء مدفوع", JS)
        self.assertIn('m=re.fullmatch(r\'/api/v1/orders/(\\d+)/cancellation\',p)', SERVER)
        self.assertIn("if p=='/api/admin/cancellations' and method=='GET':", SERVER)
        self.assertIn("admin_transition_cancellation", SERVER)
        self.assertNotIn("mark_refunded", JS)

    def test_real_admin_safety_moderation_and_safe_privacy_triage(self):
        for el in (
            "adminSafetyDialog", "adminSafetyTitle", "adminSafetyDetails",
            "adminSafetyForm", "adminSafetyId", "adminSafetyStatus",
            "adminSafetyTaskAction", "adminSafetyUserAction", "adminSafetyNote",
            "closeAdminSafety", "adminPrivacyDialog", "adminPrivacyTitle",
            "adminPrivacyDetails", "adminPrivacyForm", "adminPrivacyId",
            "adminPrivacyStatus", "adminPrivacyNote", "closeAdminPrivacy"
        ):
            self.assertIn('id="'+el+'"', HTML)
        self.assertIn('request("/api/admin/safety/reports")', JS)
        self.assertIn('request("/api/admin/safety/reports/"+id,{method:"PATCH"', JS)
        self.assertIn('request("/api/admin/privacy/"+id,{method:"PATCH"', JS)
        self.assertIn('adminSafetyReports.filter(x=>["open","in_review"].includes(x.status))', JS)
        self.assertIn('adminPrivacyRequests.filter(x=>["pending","in_progress"].includes(x.status))', JS)
        self.assertIn('if(status==="dismissed"&&(task_action||user_action))', JS)
        self.assertIn('window.confirm("هذا الإجراء سيؤثر فورًا', JS)
        self.assertIn('if(currentUser?.role!=="admin")return', JS)
        self.assertIn("مخصصة لفرز طلبات الخصوصية", HTML)
        self.assertNotIn('option value="completed"', HTML)
        self.assertNotIn('option value="delete"', HTML[HTML.index('id="adminPrivacyStatus"'):HTML.index('id="adminPrivacyNote"')])
        self.assertIn("if p.startswith('/api/admin'):", SERVER)
        self.assertIn("update_safety_report_admin(rid,u['id']", SERVER)
        self.assertIn("update_privacy_request(pid,st", SERVER)

    def test_support_and_privacy_replies_notify_actual_user_without_duplicate(self):
        self.assertIn("notify(prev['user_id'],'تحديث من دعم مِنجاز'", SERVER)
        self.assertIn("notify(pr['user_id'],'تحديث طلب الخصوصية #'+str(pid)", SERVER)
        self.assertIn("if changed:\\n                        admin_audit(u['id'],'support_updated'", SERVER)
        self.assertIn("if changed:\\n                        admin_audit(u['id'],'privacy_request_updated'", SERVER)
        self.assertIn('x.admin_note?', JS)
        self.assertIn('ملاحظة الإدارة:', JS)
        self.assertNotIn("بداية تنفيذ حذف الحساب", JS)
        self.assertIn("('completed','rejected')", SERVER)

    @unittest.skipUnless(shutil.which("node"), "Node unavailable in minimal Docker image")
    def test_javascript_parses(self):
        subprocess.run(["node", "--check", str(ROOT / "public" / "workspace-v1.js")], check=True)


if __name__ == "__main__":
    unittest.main()
