import { describe, it, expect, beforeEach, vi } from "vitest";
import { mount } from "@vue/test-utils";
import CitationRenderer from "@/components/CitationRenderer.vue";
import type { Citation, ImageInfo } from "@/api/agent";

const mockInternalCitation: Citation = {
  index: 1,
  title: "入职手册",
  platform: "internal",
  url: "",
  source_name: "",
  is_internal: true,
};

const mockExternalCitation: Citation = {
  index: 1,
  title: "微信文章标题",
  platform: "wechat",
  url: "https://mp.weixin.qq.com/s/test",
  source_name: "公司公众号",
  is_internal: false,
};

describe("CitationRenderer", () => {
  describe("text rendering", () => {
    it("renders plain text without citation markers", () => {
      const wrapper = mount(CitationRenderer, {
        props: { content: "这是一段普通的回答。" },
      });

      expect(wrapper.find(".citation-content").text()).toContain("这是一段普通的回答。");
      expect(wrapper.find("sup").exists()).toBe(false);
    });

    it("renders empty content as empty", () => {
      const wrapper = mount(CitationRenderer, {
        props: { content: "" },
      });

      expect(wrapper.find(".citation-content").text()).toBe("");
    });

    it("escapes HTML in text content", () => {
      const wrapper = mount(CitationRenderer, {
        props: { content: '<script>alert("xss")</script>' },
      });

      const html = wrapper.find(".citation-content").html();
      expect(html).toContain("&lt;script&gt;");
      expect(html).not.toContain("<script>");
    });

    it("converts newlines to <br> tags", () => {
      const wrapper = mount(CitationRenderer, {
        props: { content: "第一行\n第二行" },
      });

      const html = wrapper.find(".citation-content").html();
      expect(html).toContain("<br>");
    });
  });

  describe("citation markers", () => {
    it("renders [N] markers as sup elements", () => {
      const wrapper = mount(CitationRenderer, {
        props: { content: "根据[1]文档记载。" },
      });

      const sup = wrapper.find("sup.citation-ref");
      expect(sup.exists()).toBe(true);
      expect(sup.text()).toBe("[1]");
    });

    it("renders multiple citation markers", () => {
      const wrapper = mount(CitationRenderer, {
        props: { content: "根据[1]和[3]的说明。" },
      });

      const sups = wrapper.findAll("sup.citation-ref");
      expect(sups.length).toBe(2);
      expect(sups[0].text()).toBe("[1]");
      expect(sups[1].text()).toBe("[3]");
    });
  });

  describe("placeholder / active states", () => {
    it("shows placeholder style when citations are undefined", () => {
      const wrapper = mount(CitationRenderer, {
        props: { content: "参考[1]文档。" },
      });

      const sup = wrapper.find("sup.citation-ref");
      expect(sup.classes()).toContain("placeholder");
    });

    it("shows placeholder style when citations is empty array", () => {
      const wrapper = mount(CitationRenderer, {
        props: { content: "参考[1]文档。", citations: [] },
      });

      const sup = wrapper.find("sup.citation-ref");
      expect(sup.classes()).toContain("placeholder");
    });

    it("shows active style when citations are provided", () => {
      const wrapper = mount(CitationRenderer, {
        props: {
          content: "参考[1]文档。",
          citations: [mockInternalCitation],
        },
      });

      const sup = wrapper.find("sup.citation-ref");
      expect(sup.classes()).not.toContain("placeholder");
    });
  });

  describe("reference list", () => {
    it("does not render reference list when citations are undefined", () => {
      const wrapper = mount(CitationRenderer, {
        props: { content: "参考[1]文档。" },
      });

      expect(wrapper.find(".citation-references").exists()).toBe(false);
    });

    it("renders reference list with internal citation", () => {
      const wrapper = mount(CitationRenderer, {
        props: {
          content: "参考[1]文档。",
          citations: [mockInternalCitation],
        },
      });

      const refs = wrapper.find(".citation-references");
      expect(refs.exists()).toBe(true);
      expect(refs.text()).toContain("入职手册");
      expect(refs.text()).toContain("内部文档");
      expect(wrapper.find(".citation-item.internal").exists()).toBe(true);
    });

    it("renders reference list with external citation and link", () => {
      const wrapper = mount(CitationRenderer, {
        props: {
          content: "参考[1]文章。",
          citations: [mockExternalCitation],
        },
      });

      const refs = wrapper.find(".citation-references");
      expect(refs.exists()).toBe(true);
      expect(refs.text()).toContain("微信文章标题");
      expect(refs.text()).toContain("公司公众号");
      expect(refs.text()).toContain("查看原文");

      const link = wrapper.find(".citation-item.external a.cite-title");
      expect(link.exists()).toBe(true);
      expect(link.attributes("href")).toBe("https://mp.weixin.qq.com/s/test");
      expect(link.attributes("target")).toBe("_blank");
      expect(link.attributes("rel")).toBe("noopener noreferrer");
    });

    it("filters citations to only those referenced in content", () => {
      const extraCitation: Citation = {
        index: 2,
        title: "其他文档",
        platform: "internal",
        url: "",
        source_name: "",
        is_internal: true,
      };

      const wrapper = mount(CitationRenderer, {
        props: {
          content: "参考[1]文档。",
          citations: [mockInternalCitation, extraCitation],
        },
      });

      const refs = wrapper.find(".citation-references");
      expect(refs.text()).toContain("入职手册");
      expect(refs.text()).not.toContain("其他文档");
    });

    it("sorts citations by index ascending", () => {
      const citation3: Citation = { index: 3, title: "第三", platform: "internal", url: "", source_name: "", is_internal: true };
      const citation2: Citation = { index: 2, title: "第二", platform: "internal", url: "", source_name: "", is_internal: true };

      const wrapper = mount(CitationRenderer, {
        props: {
          content: "参考[3]和[2]。",
          citations: [citation3, citation2],
        },
      });

      const nums = wrapper.findAll(".cite-num");
      expect(nums.length).toBe(2);
      expect(nums[0].text()).toBe("[2]");
      expect(nums[1].text()).toBe("[3]");
    });
  });

  describe("platform label", () => {
    it("shows '内部文档' for internal citations", () => {
      const wrapper = mount(CitationRenderer, {
        props: {
          content: "参考[1]。",
          citations: [mockInternalCitation],
        },
      });

      expect(wrapper.text()).toContain("内部文档");
    });

    it("shows source_name for external citations", () => {
      const wrapper = mount(CitationRenderer, {
        props: {
          content: "参考[1]。",
          citations: [mockExternalCitation],
        },
      });

      expect(wrapper.text()).toContain("公司公众号");
    });

    it("falls back to platform name when source_name is empty", () => {
      const citation: Citation = {
        index: 1,
        title: "B站视频",
        platform: "bilibili",
        url: "https://bilibili.com/video/test",
        source_name: "",
        is_internal: false,
      };

      const wrapper = mount(CitationRenderer, {
        props: {
          content: "参考[1]。",
          citations: [citation],
        },
      });

      expect(wrapper.text()).toContain("bilibili");
    });
  });

  describe("inline images", () => {
    const imgCitation: Citation = {
      index: 1,
      title: "含图文章",
      platform: "wechat",
      url: "https://mp.weixin.qq.com/s/img",
      source_name: "公司公众号",
      is_internal: false,
    };

    const mockImages: ImageInfo[] = [
      { id: 1, doc_index: 1, seq: 1, url: "/api/public/images/article-images/wechat/a/abc.jpg" },
    ];

    it("renders an image card when [图N] matches the images list", () => {
      const wrapper = mount(CitationRenderer, {
        props: {
          content: "示意图[图1]如下。",
          citations: [imgCitation],
          images: mockImages,
        },
      });

      const img = wrapper.find(".img-card .chat-image");
      expect(img.exists()).toBe(true);
      expect(img.attributes("src")).toBe(mockImages[0].url);
    });

    it("shows placeholder during streaming while image is not yet resolved", () => {
      const wrapper = mount(CitationRenderer, {
        props: {
          content: "示意图[图1]如下。",
          isStreaming: true,
          images: [],
        },
      });

      expect(wrapper.find(".img-placeholder").exists()).toBe(true);
    });

    it("hides unresolved image markers when not streaming", () => {
      const wrapper = mount(CitationRenderer, {
        props: {
          content: "示意图[图1]如下。",
          isStreaming: false,
          images: [],
        },
      });

      expect(wrapper.find(".img-card").exists()).toBe(false);
      expect(wrapper.text()).not.toContain("[图1]");
    });

    it("merges consecutive image markers into one group", () => {
      const twoImages: ImageInfo[] = [
        { id: 1, doc_index: 1, seq: 1, url: "/api/public/images/1.jpg" },
        { id: 2, doc_index: 1, seq: 2, url: "/api/public/images/2.jpg" },
      ];
      const wrapper = mount(CitationRenderer, {
        props: {
          content: "图组[图1][图2]。",
          citations: [imgCitation],
          images: twoImages,
        },
      });

      expect(wrapper.findAll(".img-group").length).toBe(1);
      expect(wrapper.findAll(".img-card .chat-image").length).toBe(2);
    });

    it("shows source caption for inline image", () => {
      const wrapper = mount(CitationRenderer, {
        props: {
          content: "示意图[图1]。",
          citations: [imgCitation],
          images: mockImages,
        },
      });

      expect(wrapper.find(".img-caption").text()).toContain("含图文章");
    });
  });

  describe("citation thumbnails", () => {
    it("renders thumbnail images inside citation item when provided", () => {
      const citationWithImg: Citation = {
        index: 1,
        title: "含图文章",
        platform: "wechat",
        url: "https://mp.weixin.qq.com/s/img",
        source_name: "公司公众号",
        is_internal: false,
        images: [{ id: 1, url: "/api/public/images/1.jpg" }],
      };

      const wrapper = mount(CitationRenderer, {
        props: {
          content: "参考[1]。",
          citations: [citationWithImg],
        },
      });

      expect(wrapper.find(".citation-item .cite-thumbs .cite-thumb").exists()).toBe(true);
    });
  });
});
