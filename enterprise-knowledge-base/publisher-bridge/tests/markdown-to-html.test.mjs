import { test } from 'node:test';
import assert from 'node:assert/strict';
import { markdownToHtml } from '../src/server.mjs';

test('converts inline code', () => {
  const out = markdownToHtml('使用 `npm test` 运行');
  assert.match(out, /<code>npm test<\/code>/);
});

test('converts fenced code blocks with language', () => {
  const out = markdownToHtml('```js\nconst a = 1;\n```');
  assert.match(out, /<pre><code>const a = 1;\n<\/code><\/pre>/);
});

test('converts images and links', () => {
  const out = markdownToHtml('![图](https://x/img.png) [链接](https://x/a)');
  assert.match(out, /<img src="https:\/\/x\/img\.png" alt="图" \/>/);
  assert.match(out, /<a href="https:\/\/x\/a">链接<\/a>/);
});

test('converts headings h1 to h6', () => {
  const out = markdownToHtml('# H1\n## H2\n### H3\n#### H4\n##### H5\n###### H6');
  assert.match(out, /<h1>H1<\/h1>/);
  assert.match(out, /<h2>H2<\/h2>/);
  assert.match(out, /<h3>H3<\/h3>/);
  assert.match(out, /<h4>H4<\/h4>/);
  assert.match(out, /<h5>H5<\/h5>/);
  assert.match(out, /<h6>H6<\/h6>/);
});

test('converts bold, italic and bold-italic', () => {
  const out = markdownToHtml('**粗** *斜* ***粗斜***');
  assert.match(out, /<strong>粗<\/strong>/);
  assert.match(out, /<em>斜<\/em>/);
  assert.match(out, /<strong><em>粗斜<\/em><\/strong>/);
});

test('converts unordered and ordered lists', () => {
  const ul = markdownToHtml('- 甲\n- 乙');
  assert.match(ul, /<ul><li>甲<\/li>\n<li>乙<\/li><\/ul>/);
  const ol = markdownToHtml('1. 第一\n2. 第二');
  assert.match(ol, /<li>第一<\/li>/);
  assert.match(ol, /<li>第二<\/li>/);
});

test('converts blockquote and horizontal rule', () => {
  const out = markdownToHtml('> 引用\n\n---');
  assert.match(out, /<blockquote>引用<\/blockquote>/);
  assert.match(out, /<hr \/>/);
});

test('wraps plain paragraphs in <p>', () => {
  const out = markdownToHtml('第一段\n第二段');
  assert.match(out, /<p>第一段\n第二段<\/p>/);
});

test('preserves blank-line separated paragraphs', () => {
  const out = markdownToHtml('甲\n\n乙');
  assert.match(out, /<p>甲<\/p>/);
  assert.match(out, /<p>乙<\/p>/);
});

test('does not wrap already-generated block elements', () => {
  const out = markdownToHtml('# 标题\n\n正文');
  assert.match(out, /<h1>标题<\/h1>/);
  assert.ok(!/<p><h1>/.test(out));
});
