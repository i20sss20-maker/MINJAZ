"""Read-only premium workspace UX contract: real data, no fabricated counts."""
import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
HTML=(ROOT/'public/workspace.html').read_text(encoding='utf-8')
JS=(ROOT/'public/workspace-v1.js').read_text(encoding='utf-8')
CSS=(ROOT/'public/minjaz-signature.css').read_text(encoding='utf-8')
SERVER=(ROOT/'server.py').read_text(encoding='utf-8')


class WorkspacePolish(unittest.TestCase):
    def test_navigation_has_valid_targets_and_keyboard_support(self):
        for target in ('overview','create-section','tasks-section','proposalPanel',
                       'orders-section','profile','support-section'):
            self.assertIn('href="#'+target+'"',HTML)
            self.assertIn('id="'+target+'"',HTML)
        self.assertIn('aria-label="أقسام مساحة العمل"',HTML)
        self.assertIn('id="refreshWorkspace"',HTML)
        self.assertIn('id="navProposals"',HTML)
        self.assertIn('id="navCreate"',HTML)
        self.assertIn('show("navCreate",role==="client")',JS)
        self.assertIn('show("navProposals",role==="freelancer")',JS)
        self.assertIn('refreshWorkspace").addEventListener("click"',JS)

    def test_task_and_order_lists_use_actual_api_rows(self):
        for element in ('taskSearch','taskStatusFilter','taskItems','tasksResultCount',
                        'orderSearch','orderStatusFilter','orderItems',
                        'ordersResultCount','moreTasks','moreOrders'):
            self.assertIn('id="'+element+'"',HTML)
        self.assertIn('const tasks=filteredTasks()',JS)
        self.assertIn('const orders=filteredOrders()',JS)
        self.assertIn('currentTasks.filter(t=>',JS)
        self.assertIn('currentOrders.filter(o=>',JS)
        self.assertIn('TASK_PAGE_SIZE=20,ORDER_PAGE_SIZE=15',JS)
        self.assertIn('taskVisibleCount+=TASK_PAGE_SIZE',JS)
        self.assertIn('orderVisibleCount+=ORDER_PAGE_SIZE',JS)
        self.assertIn('tasks.slice(0,taskVisibleCount)',JS)
        self.assertIn('orders.slice(0,orderVisibleCount)',JS)
        self.assertNotIn('tasks.slice(0,40)',JS)
        self.assertNotIn('orders.slice(0,25)',JS)
        self.assertIn('request("/api/v1/tasks")',JS)
        self.assertIn('request("/api/v1/orders")',JS)

    def test_transient_network_failures_cannot_look_like_zero_real_records(self):
        self.assertIn('loadErrors.tasks=t.status!=="fulfilled"',JS)
        self.assertIn('loadErrors.orders=o.status!=="fulfilled"',JS)
        self.assertIn('loadErrors.proposals=proposals.status!=="fulfilled"',JS)
        self.assertIn('loadErrors.tasks?"—":currentTasks.length',JS)
        self.assertIn('loadErrors.orders?"—":currentOrders.length',JS)
        self.assertIn('تعذّر تحميل طلباتك الآن',JS)
        self.assertIn('تعذّر الاتصال بالمشاريع الآن',JS)
        self.assertIn('البيانات غير متاحة مؤقتًا',JS)

    def test_screen_reader_and_responsive_feedback(self):
        self.assertIn('role="status" aria-live="polite"',HTML)
        self.assertIn('id="actionToast" class="action-toast" aria-hidden="true"',HTML)
        self.assertIn('setAttribute("aria-busy","true")',JS)
        self.assertIn('removeAttribute("aria-busy")',JS)
        for token in ('.minjaz-work .work-nav','.minjaz-work .list-tools',
                      '.minjaz-work .action-toast','.minjaz-work .list-more',
                      'prefers-reduced-motion','focus-visible'):
            self.assertIn(token,CSS)

    def test_no_payment_mock_or_admin_privilege_in_frontend(self):
        self.assertNotIn('/api/v1/orders/pay',JS)
        self.assertNotIn('payment_mode=mock',JS)
        self.assertNotIn('ADMIN_EMAIL',JS)
        self.assertIn('role==="admin"',JS)
        self.assertIn('APP_ENV',SERVER)

    @unittest.skipUnless(shutil.which('node'), 'Node unavailable')
    def test_javascript_parses(self):
        subprocess.run(['node','--check',str(ROOT/'public/workspace-v1.js')],check=True)

    def test_dom_ids_unique(self):
        ids=re.findall(r'\bid="([^"]+)"',HTML)
        self.assertEqual(len(ids),len(set(ids)))


if __name__=='__main__':
    unittest.main()
