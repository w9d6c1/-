"""C1 — 种子数据批量导入测试"""

import os
import tempfile
import pytest


def _write_csv(path: str, headers: list[str], rows: list[list[str]]) -> None:
    import csv
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, quoting=csv.QUOTE_ALL)
        writer.writerow(headers)
        for row in rows:
            writer.writerow(row)


class TestImportSeedData:
    @pytest.mark.asyncio
    async def test_import_faqs_from_csv(self, db_session):
        from app.scripts.import_seed_data import import_faqs

        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as tmp:
            path = tmp.name
            tmp.close()
            _write_csv(path, ["question", "answer", "scope", "category"], [
                ["公司考勤制度", "朝九晚六，周末双休", "public", "人事制度"],
                ["退换货流程", "联系客服申请，7天内包退", "customer", "客服知识"],
            ])

        try:
            count = await import_faqs(db_session, path)
            assert count == 2

            from sqlalchemy import select
            from app.models.faq import KnowledgeFAQ
            r = await db_session.execute(select(KnowledgeFAQ).where(KnowledgeFAQ.question == "公司考勤制度"))
            faq = r.scalar_one()
            assert faq.answer == "朝九晚六，周末双休"
            assert faq.scope == "public"
        finally:
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_import_faqs_skips_duplicates(self, db_session):
        from app.scripts.import_seed_data import import_faqs

        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as tmp:
            path = tmp.name
            tmp.close()
            _write_csv(path, ["question", "answer", "scope", "category"], [
                ["唯一问题", "答案A", "public", "通用"],
                ["唯一问题", "答案B", "public", "通用"],
            ])

        try:
            count = await import_faqs(db_session, path)
            assert count == 1
        finally:
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_import_documents_from_csv(self, db_session):
        from app.scripts.import_seed_data import import_documents

        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
            path = f.name
            _write_csv(path, ["title", "content", "scope", "category"], [
                ["员工手册", "# 员工手册\n\n## 考勤\n朝九晚六", "public", "制度文件"],
            ])

        try:
            count = await import_documents(db_session, path)
            assert count == 1

            from sqlalchemy import select
            from app.models.document import KnowledgeDoc
            r = await db_session.execute(select(KnowledgeDoc).where(KnowledgeDoc.title == "员工手册"))
            doc = r.scalar_one()
            assert doc.scope == "public"
            assert doc.chunk_count > 0
        finally:
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_import_documents_skips_duplicates(self, db_session):
        from app.scripts.import_seed_data import import_documents

        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
            path = f.name
            _write_csv(path, ["title", "content", "scope", "category"], [
                ["重复标题", "内容A", "public", "通用"],
                ["重复标题", "内容B", "public", "通用"],
            ])

        try:
            count = await import_documents(db_session, path)
            assert count == 1
        finally:
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_import_synonyms_from_csv(self, db_session):
        from app.scripts.import_seed_data import import_synonyms

        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
            path = f.name
            _write_csv(path, ["word", "synonyms", "scope"], [
                ["远程办公", "居家办公;远程工作;WFH", "public"],
                ["加班", "超时工作;OT", "internal"],
            ])

        try:
            count = await import_synonyms(db_session, path)
            assert count == 2

            from sqlalchemy import select
            from app.api.admin.dictionary import Synonym
            r = await db_session.execute(select(Synonym).where(Synonym.word == "远程办公"))
            syn = r.scalar_one()
            assert "居家办公" in syn.synonyms
        finally:
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_auto_create_missing_category(self, db_session):
        from app.scripts.import_seed_data import ensure_category

        cat_id = await ensure_category(db_session, "全新分类", "customer")
        assert cat_id > 0

        cat_id_2 = await ensure_category(db_session, "全新分类", "customer")
        assert cat_id == cat_id_2

    @pytest.mark.asyncio
    async def test_empty_csv_returns_zero(self, db_session):
        from app.scripts.import_seed_data import import_faqs

        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as tmp:
            path = tmp.name
            tmp.close()
            _write_csv(path, ["question", "answer", "scope", "category"], [])

        try:
            count = await import_faqs(db_session, path)
            assert count == 0
        finally:
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_csv_with_empty_rows_skipped(self, db_session):
        from app.scripts.import_seed_data import import_faqs

        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as tmp:
            path = tmp.name
            tmp.close()
            _write_csv(path, ["question", "answer", "scope", "category"], [
                ["", "", "public", "通用"],
                ["有效问题", "有效答案", "public", "通用"],
            ])

        try:
            count = await import_faqs(db_session, path)
            assert count == 1
        finally:
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_missing_file_returns_zero(self, db_session):
        from app.scripts.import_seed_data import import_faqs

        count = await import_faqs(db_session, "/nonexistent/path.csv")
        assert count == 0

    @pytest.mark.asyncio
    async def test_import_seed_data_all(self, db_session):
        from app.scripts.import_seed_data import import_seed_data

        faq_path = None
        doc_path = None
        syn_path = None

        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
                faq_path = f.name
                _write_csv(faq_path, ["question", "answer", "scope", "category"], [
                    ["集成FAQ", "集成答案", "public", "集成分类"],
                ])

            with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
                doc_path = f.name
                _write_csv(doc_path, ["title", "content", "scope", "category"], [
                    ["集成文档", "集成内容测试", "public", "集成分类"],
                ])

            with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
                syn_path = f.name
                _write_csv(syn_path, ["word", "synonyms", "scope"], [
                    ["集成词", "词A;词B", "public"],
                ])

            result = await import_seed_data(db_session, faq_csv=faq_path, doc_csv=doc_path, syn_csv=syn_path)
            assert result["faqs"] == 1
            assert result["documents"] == 1
            assert result["synonyms"] == 1

        finally:
            for p in [faq_path, doc_path, syn_path]:
                if p and os.path.isfile(p):
                    os.unlink(p)
