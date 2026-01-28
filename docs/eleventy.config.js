import syntaxHighlight from "@11ty/eleventy-plugin-syntaxhighlight";

export default function(eleventyConfig) {
  // Syntax highlighting for code blocks
  eleventyConfig.addPlugin(syntaxHighlight);

  // Copy assets to output (includes animator in src/assets/js/animator/)
  eleventyConfig.addPassthroughCopy("src/assets");

  // Ignore task tracking directory
  eleventyConfig.ignores.add("tasks/**");

  return {
    dir: {
      input: "src",
      output: "_site",
      includes: "_includes",
      layouts: "_includes",
      data: "_data",
    },
    markdownTemplateEngine: "njk",
    htmlTemplateEngine: "njk",
  };
}
