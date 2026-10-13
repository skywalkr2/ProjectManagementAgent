import "@testing-library/jest-dom/vitest";
import { configure } from "@testing-library/react";

// A loaded machine can take longer than the default second to render a screen's first data; waiting longer costs
// nothing when it renders sooner.
configure({ asyncUtilTimeout: 4000 });
window.scrollTo = () => undefined;
