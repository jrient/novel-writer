"""
文本切分和向量化服务
"""
import re
from typing import List, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.reference import ReferenceNovel
from app.models.embedding import NovelChunk
from app.services.embedding import embedding_service


class ChunkService:
    @staticmethod
    def split_text(content: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
        """将文本切分成chunks"""
        # 按段落分割
        paragraphs = [p.strip() for p in content.split('\n') if p.strip()]

        chunks = []
        current_chunk = []
        current_length = 0

        for para in paragraphs:
            para_len = len(para)

            if current_length + para_len > chunk_size and current_chunk:
                # 保存当前chunk
                chunks.append('\n'.join(current_chunk))
                # 保留overlap
                if overlap > 0 and current_chunk:
                    current_chunk = current_chunk[-1:]
                    current_length = len(current_chunk[0])
                else:
                    current_chunk = []
                    current_length = 0

            current_chunk.append(para)
            current_length += para_len

        if current_chunk:
            chunks.append('\n'.join(current_chunk))

        return chunks

    @staticmethod
    async def process_reference(
        db: AsyncSession,
        reference_id: int,
        chunk_size: int = 500
    ) -> int:
        """处理参考小说，生成chunks和embeddings"""
        # 获取参考小说
        result = await db.execute(
            select(ReferenceNovel).where(ReferenceNovel.id == reference_id)
        )
        reference = result.scalar_one_or_none()
        if not reference:
            raise ValueError(f"Reference {reference_id} not found")

        # 读取内容
        content = reference.content
        if not content and reference.file_path:
            with open(reference.file_path, 'r', encoding='utf-8') as f:
                content = f.read()

        if not content:
            return 0

        # 切分文本
        chunks = ChunkService.split_text(content, chunk_size)

        # 批量生成embeddings (每次最多100个)
        batch_size = 100
        chunk_count = 0

        for i in range(0, len(chunks), batch_size):
            batch_chunks = chunks[i:i + batch_size]
            embeddings = await embedding_service.generate_embeddings(batch_chunks)

            # 保存到数据库
            for idx, (chunk_text, embedding) in enumerate(zip(batch_chunks, embeddings)):
                novel_chunk = NovelChunk(
                    reference_id=reference_id,
                    chunk_index=i + idx,
                    content=chunk_text,
                    char_count=len(chunk_text),
                    embedding=embedding
                )
                db.add(novel_chunk)
                chunk_count += 1

            await db.commit()

        return chunk_count


chunk_service = ChunkService()
