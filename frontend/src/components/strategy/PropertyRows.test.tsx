import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PropertyRows } from "@/components/strategy/PropertyRows";

describe("PropertyRows", () => {
  it("pairs each label with its value as a description list", () => {
    const { container } = render(
      <PropertyRows
        properties={[
          { label: "Brand", value: "Mega Toothpaste" },
          { label: "Markets", value: "UK · USA · France" },
        ]}
      />,
    );

    expect(container.querySelector("dl")).not.toBeNull();
    expect([...container.querySelectorAll("dt")].map((n) => n.textContent))
      .toEqual(["Brand", "Markets"]);
    expect([...container.querySelectorAll("dd")].map((n) => n.textContent))
      .toEqual(["Mega Toothpaste", "UK · USA · France"]);
  });

  it("renders an em-dash placeholder for a value the plan has not set", () => {
    render(<PropertyRows properties={[{ label: "Creative", value: null }]} />);

    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("dims an unset value and emphasises a set one", () => {
    const { container } = render(
      <PropertyRows
        properties={[
          { label: "Brand", value: "Mega Toothpaste" },
          { label: "Creative", value: null },
        ]}
      />,
    );

    const [set, unset] = container.querySelectorAll("dd");
    expect(set).toHaveClass("font-semibold");
    expect(unset).not.toHaveClass("font-semibold");
  });

  it("renders an empty list without a row", () => {
    const { container } = render(<PropertyRows properties={[]} />);

    expect(container.querySelectorAll("dt")).toHaveLength(0);
  });
});
