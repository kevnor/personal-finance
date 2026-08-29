import { createContext, useContext } from "react";

// Categories and accounts, fetched once when the app signs in and shared by
// every screen. Both are small, change rarely, and are needed almost
// everywhere — Review needs the category list to offer choices, Add needs
// the accounts, History needs labels for every row.
const AppDataContext = createContext(null);

export function AppDataProvider({ value, children }) {
  return <AppDataContext.Provider value={value}>{children}</AppDataContext.Provider>;
}

export function useAppData() {
  const value = useContext(AppDataContext);
  if (!value) throw new Error("useAppData used outside AppDataProvider");
  return value;
}

/**
 * Build the lookup helpers from the fetched lists.
 *
 * `labelFor` falls back to the identifier rather than to an empty string: if
 * the server ever ships a category the label map missed, the screen shows
 * "Groceries" rather than a blank — visibly wrong, which is what gets it
 * fixed. A server-side test asserts the fallback is never actually used.
 */
export function buildAppData(categories, accounts) {
  const byName = new Map(categories.map((c) => [c.name, c]));
  return {
    categories,
    accounts,
    labelFor: (name) => (name ? byName.get(name)?.label ?? name : "—"),
    categoryByName: (name) => byName.get(name),
    // Expense categories are what a person recategorises a purchase into;
    // offering them Salary or Credit card payment in that list is noise.
    expenseCategories: categories.filter((c) => c.kind === "expense"),
  };
}
