# BISTEC GLOBAL

## Vega Construction — System Enhancements

**Project:** Vega Construction — Material Price List, BSR & Payment Management System

**Document Purpose:** This document outlines the proposed functional enhancements identified for the Vega Construction system, covering project access control, pricing configuration, BSR item management, and expense/payment tracking.

---

## Proposed Enhancements

### 1. User-Scoped Project Visibility

**Module:** Project Access

The logged-in user should only be able to view projects that were created by that particular user.

This ensures data privacy between users and prevents users from seeing projects that are not relevant to them.

---

### 2. Unique Basic Price & Basic Rate per Project

**Module:** Project Setup

The basic price and basic rate must be configurable uniquely for each project, rather than shared across all projects.

This is required because pricing can vary between projects depending on the time duration or market conditions at the time the project was created.

---

### 3. Material Description for BSR Items

**Module:** BSR (Basic Schedule of Rates)

When adding an item under BSR, the user must be able to type in a free-text description of the materials included within that particular BSR category.

This gives clarity on what is covered under each BSR line item and reduces ambiguity for future reference.

---

### 4. Partial/Full Payment Allocation for Expenses

**Module:** Expense Management

Under the expense section, the user must be able to add an expense and allocate the amount paid against it, whether the payment is partial or full.

Where an expense is only partially paid, the system should automatically calculate and display the outstanding balance remaining to be paid.

---

### 5. Payment Summary for Suppliers & Sub-Contractors

**Module:** Payment Management

A new Payment Summary view should be added to allow the user to record payments (full or partial) made to a specific supplier or sub-contractor.

This summary should display the outstanding payments per supplier/sub-contractor, and highlight the supplier or sub-contractor who has been paid the most to date.

---

### 6. Row-Wise, Stage-Based Expense Entry with Cost Highlighting

**Module:** Expense Management

When adding an expense, the user should be able to enter data row-wise for each stage, allowing expenses to be captured on an item-by-item basis.

Based on the entered data, the system should automatically highlight in red the most costly item(s), so the user can quickly identify which items are driving higher costs and which are relatively low-cost.

---

### 7. To Add a Factor in the BSR Section

Once the BSR data is added, keep a section for the user to add the factor to get the amount required for an estimation. The user must be able to select whether it is to be multiplied or divided and allow the user to enter a number. Based on the number and the selected multiplication or division the result must be displayed.

---

**Prepared by:** BISTEC Global — Project Delivery Team
