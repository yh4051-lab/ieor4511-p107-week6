"""Real local HTTP tests for the isolated four-strategy research lab."""
from copy import deepcopy
import hashlib
import http.client
import io
import json
from pathlib import Path
import sys
import threading
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server


class TaxLabHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=server.AppServer(('127.0.0.1',0))
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join(timeout=2)

    def request(self,method,path,body=None,headers=None):
        connection=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=120)
        connection.request(method,path,body=body,headers=headers or {})
        response=connection.getresponse()
        answer=response.status,response.read(),dict(response.getheaders())
        connection.close()
        return answer

    def payload(self):
        defaults=server.tax_lab_defaults()
        config=deepcopy(defaults['demo_config']);config['end_date']='2020-03-31'
        return dict(config=config,data_source='demo',optimization=defaults['defaults']['optimization'],
                    sensitivities=dict(enabled=True,financing_rates=[5],borrow_rates=[1]),
                    monte_carlo=dict(enabled=True,paths=2,seed=4511))

    def test_routes_and_origin_restrictions(self):
        for path in ('/tax-lab','/tax-lab.js','/tax-lab.css','/','/studies','/assumptions'):
            with self.subTest(path=path):self.assertEqual(self.request('GET',path)[0],200)
        status,raw,_=self.request('GET','/api/tax-lab/defaults')
        self.assertEqual(status,200)
        self.assertIn('demo_config',json.loads(raw))
        self.assertEqual(self.request('GET','/tax-lab',headers={
            'Sec-Fetch-Site':'cross-site','Sec-Fetch-Mode':'navigate'})[0],200)
        self.assertEqual(self.request('GET','/api/tax-lab/defaults',headers={
            'Origin':'https://unrelated.example'})[0],403)

    def test_real_four_strategy_simulation_and_frozen_export(self):
        status,raw,_=self.request('POST','/api/tax-lab/run',json.dumps(self.payload()),{'Content-Type':'application/json'})
        self.assertEqual(status,200,raw.decode())
        r=json.loads(raw)
        self.assertEqual(r['data_kind'],'synthetic')
        self.assertEqual(set(r['strategies']),set('ABCD'))
        self.assertEqual(len(r['comparison']),4)
        self.assertTrue(r['strategies']['D']['optimizer_decisions'])
        self.assertEqual(r['sensitivity']['summary']['completed'],1)
        self.assertEqual(r['monte_carlo']['summary']['completed'],2)
        for run in r['strategies'].values():
            self.assertAlmostEqual(run['daily'][-1]['total_investor_wealth'],run['summary']['terminal_after_tax_wealth'])
            self.assertEqual(run['daily'][-1]['embedded_tax_liability_estimate'],0)
            self.assertLess(run['summary']['max_wealth_identity_error'],.001)
        status,raw,headers=self.request('GET','/api/tax-lab/download/'+r['run_id'])
        self.assertEqual(status,200)
        self.assertIn('application/zip',headers['Content-Type'])
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            self.assertIsNone(z.testzip())
            self.assertIn('D/optimizer_decisions.csv',z.namelist())
            self.assertIn('comparison.csv',z.namelist())
            self.assertEqual(json.loads(z.read('input.json'))['source_kind'],'demo')
            for name,digest in json.loads(z.read('FILE_MANIFEST.json')).items():
                self.assertEqual(hashlib.sha256(z.read(name)).hexdigest(),digest)

    def test_invalid_inputs_and_parallel_guard(self):
        headers={'Content-Type':'application/json'}
        self.assertEqual(self.request('POST','/api/tax-lab/run','{}',headers)[0],400)
        payload=self.payload();payload['optimization']['long_cap_pct']=10
        self.assertEqual(self.request('POST','/api/tax-lab/run',json.dumps(payload),headers)[0],400)
        self.server.tax_lab_busy.acquire()
        try:self.assertEqual(self.request('POST','/api/tax-lab/run','{}',headers)[0],409)
        finally:self.server.tax_lab_busy.release()
        self.assertEqual(self.request('GET','/api/tax-lab/download/unknown')[0],404)


if __name__=='__main__':unittest.main()
