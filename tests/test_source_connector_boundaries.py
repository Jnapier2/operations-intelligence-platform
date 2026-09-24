"""Offline adapter contract tests; all files and inputs are disposable fixtures.

Copyright © 2026 Gateway Information Group LLC. All rights reserved.
"""
from __future__ import annotations
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
# Standalone discovery does not load the server, storage, or provider adapters.
module_path = Path(os.environ.get('OIAP_TEST_MODULE', str(ROOT / 'tools/source_connectors.py')))
spec = importlib.util.spec_from_file_location('oiap_source_adapter_under_test', module_path)
sc = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = sc
spec.loader.exec_module(sc)


class SourceConnectorBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'config').mkdir()
        (self.root / 'data').mkdir()
        self.path = self.root / 'data/source.csv'
        self.raw = b'\xef\xbb\xbfcol\r\nvalue\r\n'
        self.path.write_bytes(self.raw)
        self.config = self.root / 'config/source_connectors.json'
        self.entry = {'id':'fixture', 'type':'local_csv', 'enabled':True,
                      'path':'data/source.csv', 'max_bytes':1024,
                      'dataset_name':'Fixture dataset','source_name':'Fixture source'}
        self.payload = {'schema_version':1, 'connectors':[self.entry]}
        self.save()
        for name,value in (('ROOT',self.root),('CONFIG',self.config)):
            patch = mock.patch.object(sc,name,value);patch.start();self.addCleanup(patch.stop)

    def save(self):
        self.config.write_text(json.dumps(self.payload),encoding='utf-8')

    def test_valid_snapshot_preserves_original_digest_and_bom_decoding(self):
        r=sc.read_snapshot('fixture')
        self.assertEqual(r.csv_text,'col\r\nvalue\r\n')
        self.assertEqual(r.content_sha256,hashlib.sha256(self.raw).hexdigest())
        self.assertEqual(r.byte_count,len(self.raw))
        self.assertEqual((r.dataset_name,r.source_name),('Fixture dataset','Fixture source'))
        self.assertEqual(self.path.read_bytes(),self.raw)

    def test_enabled_false_does_not_open_source(self):
        self.entry['enabled']=False;self.save()
        with self.assertRaisesRegex(RuntimeError,'disabled'):
            sc.read_snapshot('fixture')

    def test_string_false_is_not_enabled(self):
        self.entry['enabled']='false';self.save()
        with self.assertRaises(RuntimeError): sc.read_snapshot('fixture')

    def test_other_nonboolean_enabled_values_are_rejected(self):
        for value in (1,0,'true','0',[],{},None):
            with self.subTest(value=value):
                self.entry['enabled']=value;self.save()
                with self.assertRaises(RuntimeError): sc.read_snapshot('fixture')

    def test_omitted_enabled_remains_disabled(self):
        self.entry.pop('enabled');self.save()
        with self.assertRaisesRegex(RuntimeError,'disabled'): sc.read_snapshot('fixture')

    def test_invalid_byte_limits_are_not_defaulted_or_coerced(self):
        for value in (0,-1,True,False,1.5,'32',None,8*1024*1024+1):
            with self.subTest(value=value):
                self.entry['max_bytes']=value;self.save()
                with self.assertRaises(RuntimeError): sc.read_snapshot('fixture')

    def test_missing_byte_limit_uses_existing_default(self):
        self.entry.pop('max_bytes');self.save()
        self.assertEqual(sc.read_snapshot('fixture').byte_count,len(self.raw))

    def test_exact_byte_limit_accepted_and_one_byte_over_rejected(self):
        self.entry['max_bytes']=len(self.raw);self.save()
        self.assertEqual(sc.read_snapshot('fixture').byte_count,len(self.raw))
        self.path.write_bytes(self.raw+b'x')
        with self.assertRaises(RuntimeError): sc.read_snapshot('fixture')

    def test_source_does_not_use_unbounded_read_bytes(self):
        with mock.patch.object(Path,'read_bytes',side_effect=AssertionError('unbounded read_bytes')):
            self.assertEqual(sc.read_snapshot('fixture').byte_count,len(self.raw))

    def test_regular_reads_supply_a_finite_byte_limit(self):
        if not hasattr(sc,'os'):
            self.fail('Adapter does not use a checked, bounded descriptor read')
        real=sc.os.fdopen; limits=[]
        class Reader:
            def __init__(self,handle): self.handle=handle
            def __enter__(self): return self
            def __exit__(self,*args): return self.handle.__exit__(*args)
            def fileno(self): return self.handle.fileno()
            def read(self,limit=-1):
                limits.append(limit)
                return self.handle.read(limit)
        with mock.patch.object(sc.os,'fdopen',side_effect=lambda *a,**k:Reader(real(*a,**k))):
            sc.read_snapshot('fixture')
        self.assertEqual(limits, [sc.MAX_REGISTRY_BYTES+1,1025])

    def test_registry_read_is_also_bounded(self):
        with mock.patch.object(sc,'MAX_REGISTRY_BYTES',32,create=True):
            with self.assertRaises(RuntimeError): sc.load_registry()

    def test_duplicate_json_enabled_key_rejected(self):
        text=json.dumps(self.payload).replace('"enabled": true','"enabled": false, "enabled": true')
        self.config.write_text(text,encoding='utf-8')
        with self.assertRaises(RuntimeError): sc.read_snapshot('fixture')

    def test_duplicate_json_top_level_key_rejected(self):
        text=json.dumps(self.payload).replace('"schema_version": 1','"schema_version": 2, "schema_version": 1')
        self.config.write_text(text,encoding='utf-8')
        with self.assertRaises(RuntimeError): sc.load_registry()

    def test_invalid_registry_shapes_return_controlled_error(self):
        for value in ([],None,{'schema_version':True,'connectors':[]},
                      {'schema_version':1.5,'connectors':[]},
                      {'schema_version':'1','connectors':[]},
                      {'schema_version':1,'connectors':{}},
                      {'schema_version':1}, {'schema_version':1,'connectors':[42]}):
            with self.subTest(value=value):
                self.config.write_text(json.dumps(value),encoding='utf-8')
                with self.assertRaises(RuntimeError): sc.load_registry()

    def test_unknown_connector_preserves_keyerror_contract(self):
        with self.assertRaises(KeyError): sc.read_snapshot('absent')

    def test_duplicate_ids_are_rejected(self):
        self.payload['connectors']=[self.entry,dict(self.entry)];self.save()
        with self.assertRaises(RuntimeError): sc.load_registry()

    def test_nonstring_identifier_rejected(self):
        self.entry['id']=7;self.save()
        with self.assertRaises(RuntimeError): sc.load_registry()

    def test_unsupported_adapter_does_not_fetch(self):
        self.entry['type']='http_csv';self.save()
        with self.assertRaisesRegex(RuntimeError,'Unsupported'): sc.read_snapshot('fixture')

    def test_symlink_to_inside_root_is_rejected(self):
        target=self.root/'data/real.csv';target.write_bytes(self.raw)
        self.path.unlink()
        try:self.path.symlink_to(target)
        except (OSError,NotImplementedError):self.skipTest('Symlink capability unavailable')
        with self.assertRaises(RuntimeError): sc.read_snapshot('fixture')

    def test_linked_parent_inside_root_is_rejected(self):
        target=self.root/'data'
        alias=self.root/'alias'
        try:alias.symlink_to(target,target_is_directory=True)
        except (OSError,NotImplementedError):self.skipTest('Symlink capability unavailable')
        self.entry['path']='alias/source.csv';self.save()
        with self.assertRaises(RuntimeError): sc.read_snapshot('fixture')

    def test_registry_symlink_is_rejected(self):
        target=self.root/'registry.json';target.write_bytes(self.config.read_bytes());self.config.unlink()
        try:self.config.symlink_to(target)
        except (OSError,NotImplementedError):self.skipTest('Symlink capability unavailable')
        with self.assertRaises(RuntimeError): sc.load_registry()

    def test_invalid_paths_rejected_cross_platform(self):
        for value in ('../outside.csv','/tmp/outside.csv','C:/outside.csv',
                      r'C:\outside.csv',r'..\outside.csv','data/source.csv:stream','',None,7):
            with self.subTest(value=value):
                self.entry['path']=value;self.save()
                with self.assertRaises((RuntimeError,FileNotFoundError)): sc.read_snapshot('fixture')

    def test_nonregular_source_is_rejected_before_reading(self):
        self.path.unlink();self.path.mkdir()
        with self.assertRaises(RuntimeError): sc.read_snapshot('fixture')

    def test_invalid_utf8_registry_has_controlled_error(self):
        self.config.write_bytes(b'private-fixture\xff')
        with self.assertRaises(RuntimeError) as exc:sc.load_registry()
        self.assertNotIn('private-fixture',str(exc.exception))

    def test_nonfinite_json_values_at_any_depth_are_rejected(self):
        for value in ('NaN','Infinity','1e400','-1e400'):
            with self.subTest(value=value):
                self.config.write_text(json.dumps(self.payload)[:-1]+',"note":['+value+']}',encoding='utf-8')
                with self.assertRaises(RuntimeError):sc.load_registry()

    def test_documented_default_registry_remains_compatible(self):
        self.payload=json.loads((ROOT/'config/source_connectors.json').read_text(encoding='utf-8'))
        p=self.root/self.payload['connectors'][0]['path'];p.parent.mkdir(parents=True);p.write_bytes(self.raw);self.save()
        self.assertEqual(sc.read_snapshot('demo-local').csv_text,'col\r\nvalue\r\n')


    def test_empty_source_is_preserved_for_downstream_csv_validation(self):
        self.path.write_bytes(b'')
        value=sc.read_snapshot('fixture')
        self.assertEqual(value.byte_count,0)
        self.assertEqual(value.csv_text,'')
        self.assertEqual(value.content_sha256,hashlib.sha256(b'').hexdigest())

    def test_source_mutation_during_read_is_rejected(self):
        real=sc.os.fdopen; reads=[]; source=self.path
        class Reader:
            def __init__(self,handle): self.handle=handle
            def __enter__(self):return self
            def __exit__(self,*a):return self.handle.__exit__(*a)
            def fileno(self):return self.handle.fileno()
            def read(self,limit=-1):
                data=self.handle.read(limit);reads.append(limit)
                if len(reads)==2:source.write_bytes(data+b'new-bytes')
                return data
        with mock.patch.object(sc.os,'fdopen',side_effect=lambda *a,**k:Reader(real(*a,**k))):
            with self.assertRaisesRegex(RuntimeError,'changed while reading'):sc.read_snapshot('fixture')

    def test_replaced_file_is_rejected_before_reading(self):
        # Match the adapter's canonical root, not a temporary alias/short name.
        real=sc.os.open; path=self.path.resolve(strict=True); injected=[]
        def replacement(target,flags,*args,**kwargs):
            if Path(target)==path:
                other=path.with_name('replacement.csv');other.write_bytes(b'new file')
                os.replace(other,path)
                injected.append(path)
            return real(target,flags,*args,**kwargs)
        with mock.patch.object(sc.os,'open',side_effect=replacement):
            with self.assertRaisesRegex(RuntimeError,'changed before reading'):sc.read_snapshot('fixture')
        self.assertEqual(injected, [path], 'Replacement fault must reach the source open')

    def test_source_descriptor_closes_on_oversize_rejection(self):
        self.entry['max_bytes']=1;self.save()
        real=sc.os.fdopen;handles=[]
        def opened(*a,**k):
            h=real(*a,**k);handles.append(h);return h
        with mock.patch.object(sc.os,'fdopen',side_effect=opened):
            with self.assertRaises(RuntimeError):sc.read_snapshot('fixture')
        self.assertEqual(len(handles),2)
        self.assertTrue(all(h.closed for h in handles))

    def test_registry_connector_count_is_bounded(self):
        self.payload['connectors']=[self.entry,dict(self.entry,id='second')];self.save()
        with mock.patch.object(sc,'MAX_CONNECTORS',1,create=True):
            with self.assertRaises(RuntimeError):sc.load_registry()

    def test_foreign_working_directory_does_not_change_source_authority(self):
        caller=self.root/'caller';caller.mkdir();old=Path.cwd()
        try:
            os.chdir(caller)
            self.assertEqual(sc.read_snapshot('fixture').content_sha256,hashlib.sha256(self.raw).hexdigest())
        finally:os.chdir(old)
        self.assertEqual(list(caller.iterdir()),[])

    def test_reparse_attribute_is_rejected_without_opening(self):
        from types import SimpleNamespace
        # Resolve before patching lstat so the injected attribute cannot affect
        # fixture setup. The production lexical link/reparse check is unchanged.
        real=Path.lstat; target=self.path.resolve(strict=True); injected=[]
        def attributed(path,*a,**k):
            info=real(path,*a,**k)
            if path==target:
                injected.append(target)
                return SimpleNamespace(st_mode=info.st_mode,st_file_attributes=0x400)
            return info
        # Exercise source-path handling directly; no registry or source is opened.
        with mock.patch.object(Path,'lstat',new=attributed),mock.patch.object(sc.os,'open') as opened:
            with self.assertRaisesRegex(RuntimeError,'reparse'):sc._project_file('data/source.csv')
            opened.assert_not_called()
        self.assertEqual(injected, [target], 'Reparse fault must reach the source lstat')

    def test_fault_injection_uses_canonical_target_with_aliased_root(self):
        # A real parent/.. alias needs no symlink privilege on Windows. It
        # exercises different spellings of the same fixture, not a new source.
        marker=self.root/'path spelling';marker.mkdir()
        alias=marker/'..'
        self.assertNotEqual(alias, self.root.resolve(strict=True))
        self.assertTrue(alias.samefile(self.root))
        self.root=alias;self.path=alias/'data/source.csv'
        with mock.patch.object(sc,'ROOT',alias),mock.patch.object(sc,'CONFIG',alias/'config/source_connectors.json'):
            for name in ('test_reparse_attribute_is_rejected_without_opening',
                         'test_replaced_file_is_rejected_before_reading'):
                with self.subTest(injected_fault=name):
                    self.path.write_bytes(self.raw)
                    getattr(self,name)()


class SourceConnectorStoreIntegrationTests(unittest.TestCase):
    """Use the real adapter, SQLite migrations, store, and API with synthetic data."""

    def setUp(self):
        tools = str(ROOT / "tools")
        if tools not in sys.path:
            sys.path.insert(0, tools)
        import source_connectors
        import operational_store
        import platform_api
        self.adapter = source_connectors
        self.store_module = operational_store
        self.api_module = platform_api
        self.assertIs(operational_store.read_snapshot, source_connectors.read_snapshot)
        self.temp = tempfile.TemporaryDirectory(prefix="oiap-connector-integration-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "config").mkdir()
        (self.root / "data").mkdir()
        self.source = self.root / "data/source.csv"
        self.source.write_bytes((ROOT / "public/data/service_requests_demo.csv").read_bytes())
        self.config = self.root / "config/source_connectors.json"
        self.entry = {"id": "demo-local", "type": "local_csv", "enabled": True,
                      "path": "data/source.csv", "max_bytes": 8 * 1024 * 1024,
                      "dataset_name": "Synthetic integration dataset", "source_name": "Disposable fixture"}
        self.save_registry()
        for name, value in (("ROOT", self.root), ("CONFIG", self.config)):
            patch = mock.patch.object(self.adapter, name, value)
            patch.start()
            self.addCleanup(patch.stop)
        self.store = operational_store.OperationalStore(self.root / "state/operations.db")

    def save_registry(self):
        self.config.write_text(json.dumps({"schema_version": 1, "connectors": [self.entry]}), encoding="utf-8")

    def state(self):
        with self.store.connect() as conn:
            runs = [tuple(row) for row in conn.execute("SELECT * FROM ingestion_runs ORDER BY run_id")]
            schedule = [tuple(row) for row in conn.execute("SELECT * FROM refresh_schedule ORDER BY schedule_id")]
            records = conn.execute("SELECT COUNT(*) FROM service_requests").fetchone()[0]
        return runs, schedule, records

    def assert_refresh_rejected_without_database_change(self):
        before = self.state()
        with self.assertRaises(RuntimeError):
            self.store.run_scheduled_refresh(force=True)
        self.assertEqual(self.state(), before)

    def test_demo_ingestion_uses_real_adapter_and_remains_idempotent(self):
        original = self.source.read_bytes()
        first = self.store.ensure_demo_ingested()
        second = self.store.ensure_demo_ingested()
        self.assertEqual((first["status"], first["rowCount"], first["trustedRowCount"]), ("accepted", 1354, 1335))
        self.assertEqual(first["qualityScore"], 97.6)
        self.assertEqual(second["status"], "unchanged")
        self.assertEqual(first["runId"], second["runId"])
        self.assertEqual(self.source.read_bytes(), original)

    def test_scheduled_refresh_updates_only_after_success(self):
        first = self.store.run_scheduled_refresh(force=True)
        second = self.store.run_scheduled_refresh(force=True)
        self.assertEqual(first["status"], "accepted")
        self.assertEqual(second["status"], "unchanged")
        self.assertEqual(first["runId"], second["runId"])
        with self.store.connect() as conn:
            row = conn.execute("SELECT * FROM refresh_schedule WHERE schedule_id='demo-local'").fetchone()
            self.assertEqual(row["last_result"], "unchanged")
            self.assertTrue(row["last_checked_at"])
            self.assertEqual(row["next_due_at"], second["nextDueAt"])

    def test_disabled_connector_cannot_record_a_successful_refresh(self):
        self.entry["enabled"] = False
        self.save_registry()
        self.assert_refresh_rejected_without_database_change()

    def test_string_false_cannot_ingest_through_scheduled_refresh(self):
        self.entry["enabled"] = "false"
        self.save_registry()
        self.assert_refresh_rejected_without_database_change()

    def test_oversize_source_cannot_advance_schedule(self):
        self.entry["max_bytes"] = 10
        self.save_registry()
        self.assert_refresh_rejected_without_database_change()

    def test_linked_source_cannot_ingest_through_real_store(self):
        link = self.root / "data/linked.csv"
        try:
            link.symlink_to(self.source)
        except (OSError, NotImplementedError):
            self.skipTest("OS does not permit a synthetic symbolic link")
        self.entry["path"] = "data/linked.csv"
        self.save_registry()
        self.assert_refresh_rejected_without_database_change()

    def test_duplicate_registry_fields_cannot_create_ingestion(self):
        content = self.config.read_text(encoding="utf-8").replace('"enabled": true', '"enabled": false, "enabled": true')
        self.config.write_text(content, encoding="utf-8")
        self.assert_refresh_rejected_without_database_change()

    def test_bom_snapshot_preserves_existing_ingestion_semantics(self):
        self.source.write_bytes(b"\xef\xbb\xbf" + self.source.read_bytes())
        snapshot = self.adapter.read_snapshot("demo-local")
        self.assertEqual(snapshot.content_sha256, hashlib.sha256(self.source.read_bytes()).hexdigest())
        self.assertFalse(snapshot.csv_text.startswith("\ufeff"))
        result = self.store.ensure_demo_ingested()
        self.assertEqual((result["status"], result["rowCount"]), ("accepted", 1354))

    def test_api_denies_unauthenticated_refresh_before_adapter_access(self):
        api = self.api_module.PlatformApi(self.store, release_passed=True)
        with mock.patch.object(self.store_module, "read_snapshot") as read:
            result = api.handle_post("/api/refresh", {"Host": "127.0.0.1:8765", "Content-Type": "application/json"}, b"{}")
            self.assertEqual(result.status, 401)
            read.assert_not_called()


if __name__=='__main__':unittest.main()
