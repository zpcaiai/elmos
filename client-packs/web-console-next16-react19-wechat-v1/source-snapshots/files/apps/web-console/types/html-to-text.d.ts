declare module "html-to-text" {
  export type HtmlToTextOptions = {
    baseElements?: { selectors: string[] };
    limits?: {
      maxChildNodes?: number;
      maxDepth?: number;
      maxBaseElements?: number;
    };
    selectors?: Array<{
      selector: string;
      format?: "skip";
      options?: { ignoreHref?: boolean };
    }>;
    wordwrap?: false | number;
  };

  export function convert(html: string, options?: HtmlToTextOptions): string;
}
