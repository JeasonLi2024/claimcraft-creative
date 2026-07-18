import io
import json
import os
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.utils import timezone

from api.models import Case, ComplaintTemplate, DocumentVersion, Evidence, RespondTemplate, TimelineNode
from api.services.export_service import export_evidence_package, generate_export_text
from api.services.pdf_service import (
    build_latex_source,
    build_pandoc_markdown,
    generate_complaint_pdf,
    generate_word_document,
)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix='claimcraft-export-tests-'))
class ExportServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='export-owner')
        self.case = Case.objects.create(title='导出测试', owner=self.user)
        ComplaintTemplate.objects.create(
            case=self.case,
            template_type='platform',
            title='投诉书',
            content='事实与理由\n诉求：退款',
        )
        self.evidence = Evidence.objects.create(
            case=self.case,
            code='../危险编号',
            evidence_type='聊天记录',
            description='联系电话 13800138000',
            source_time=timezone.now(),
            has_sensitive_info=True,
        )
        self.evidence.image.save('proof.jpg', ContentFile(b'not-a-real-image'), save=True)
        TimelineNode.objects.create(
            case=self.case,
            datetime=None,
            event='时间尚待确认',
            related_evidence_codes=self.evidence.code,
        )

    def tearDown(self):
        for image_field in (self.evidence.image, self.evidence.masked_image):
            if image_field:
                try:
                    os.remove(image_field.path)
                except FileNotFoundError:
                    pass

    def test_text_export_masks_document_and_evidence_and_handles_null_timeline(self):
        content = generate_export_text(self.case, masked=True)
        self.assertIn('138****8000', content)
        self.assertNotIn('13800138000', content)
        self.assertIn('时间待确认', content)

    def test_zip_uses_safe_archive_paths_and_contains_manifest(self):
        package = export_evidence_package(self.case)
        with zipfile.ZipFile(io.BytesIO(package.getvalue())) as archive:
            names = archive.namelist()
            self.assertIn('complaint.txt', names)
            self.assertIn('manifest.json', names)
            self.assertFalse(any('../' in name or name.startswith('/') for name in names))
            self.assertIn('timeline.txt', names)
            self.assertIn('evidence_list.txt', names)
            self.assertEqual(len([name for name in names if name.startswith('images/')]), 1)
            self.assertTrue(archive.read('complaint.txt').startswith(b'\xef\xbb\xbf'))
            timeline = archive.read('timeline.txt').decode('utf-8-sig')
            self.assertIn('时间待确认', timeline)
            self.assertIn('关联证据', timeline)
            manifest = json.loads(archive.read('manifest.json'))
            self.assertEqual(manifest['document_type'], 'complaint')
            self.assertEqual(
                manifest['image_policy'], 'original_and_existing_masked'
            )
            self.assertEqual(manifest['image_count'], 1)
            self.assertEqual(manifest['original_image_count'], 1)
            self.assertEqual(manifest['masked_image_count'], 0)
            self.assertEqual(manifest['images'][0]['source'], 'original_upload')
            self.assertEqual(manifest['images'][0]['code'], self.evidence.code)

    def test_zip_adds_existing_masked_image_with_explicit_name(self):
        self.evidence.masked_image.save(
            'masked-proof.jpg',
            ContentFile(b'masked-image'),
            save=False,
        )
        self.evidence.mask_status = 'done'
        self.evidence.save(update_fields=['masked_image', 'mask_status'])

        package = export_evidence_package(self.case)
        with zipfile.ZipFile(io.BytesIO(package.getvalue())) as archive:
            names = archive.namelist()
            masked_names = [
                name for name in names if name.startswith('images/masked/')
            ]
            self.assertEqual(len(masked_names), 1)
            self.assertIn('_masked.jpg', masked_names[0])
            manifest = json.loads(archive.read('manifest.json'))
            self.assertEqual(manifest['original_image_count'], 1)
            self.assertEqual(manifest['masked_image_count'], 1)
            self.assertEqual(manifest['image_count'], 2)
            self.assertTrue(any(
                item['source'] == 'masked_derivative'
                for item in manifest['images']
            ))

    def test_missing_image_is_reported_in_manifest(self):
        os.remove(self.evidence.image.path)
        package = export_evidence_package(self.case)
        with zipfile.ZipFile(io.BytesIO(package.getvalue())) as archive:
            manifest = json.loads(archive.read('manifest.json'))
            self.assertEqual(manifest['images'], [])
            self.assertEqual(manifest['image_count'], 0)
            self.assertEqual(manifest['original_image_count'], 0)
            self.assertEqual(manifest['masked_image_count'], 0)
            self.assertEqual(manifest['missing_image_count'], 1)
            self.assertEqual(manifest['missing_images'][0]['code'], self.evidence.code)

    def test_respond_case_exports_respond_document(self):
        self.case.case_mode = 'respond'
        self.case.save(update_fields=['case_mode'])
        RespondTemplate.objects.create(
            case=self.case,
            template_type='platform',
            title='反证答辩书',
            content='答辩正文',
        )
        content = generate_export_text(self.case)
        self.assertIn('反证答辩书', content)
        self.assertIn('答辩正文', content)

    def test_latex_and_word_sources_use_latest_edited_document_and_original_image(self):
        DocumentVersion.objects.create(
            case=self.case,
            document_type='complaint',
            version=1,
            title='用户修改后的投诉书',
            content='用户修改后的正文 & 特殊字符',
            created_by_type='user',
        )
        self.evidence.masked_image.save(
            'masked-proof.jpg', ContentFile(b'masked-image'), save=False
        )
        self.evidence.mask_status = 'done'
        self.evidence.save(update_fields=['masked_image', 'mask_status'])

        latex = build_latex_source(self.case)
        markdown = build_pandoc_markdown(self.case)
        self.assertIn('用户修改后的投诉书', latex)
        self.assertIn(r'用户修改后的正文 \& 特殊字符', latex)
        self.assertIn(self.evidence.image.path, latex)
        self.assertNotIn(self.evidence.masked_image.path, latex)
        self.assertIn('用户修改后的正文', markdown)
        self.assertIn(Path(self.evidence.image.path).resolve().as_uri(), markdown)
        self.assertNotIn(Path(self.evidence.masked_image.path).resolve().as_uri(), markdown)

    @patch('api.services.pdf_service.subprocess.run')
    def test_pdf_converter_returns_xelatex_output(self, run):
        def write_pdf(command, cwd, **kwargs):
            Path(cwd, 'document.pdf').write_bytes(b'%PDF-1.7 generated')
            return type('Result', (), {'returncode': 0, 'stdout': '', 'stderr': ''})()

        run.side_effect = write_pdf
        pdf = generate_complaint_pdf(self.case)
        self.assertTrue(pdf.getvalue().startswith(b'%PDF'))
        self.assertEqual(run.call_args.args[0][0], 'xelatex')
        self.assertIn('-no-shell-escape', run.call_args.args[0])

    @patch('api.services.pdf_service.subprocess.run')
    def test_word_converter_returns_pandoc_output(self, run):
        def write_docx(command, cwd, **kwargs):
            Path(cwd, 'document.docx').write_bytes(b'PK docx')
            return type('Result', (), {'returncode': 0, 'stdout': '', 'stderr': ''})()

        run.side_effect = write_docx
        word = generate_word_document(self.case)
        self.assertTrue(word.getvalue().startswith(b'PK'))
        self.assertEqual(run.call_args.args[0][0], 'pandoc')
