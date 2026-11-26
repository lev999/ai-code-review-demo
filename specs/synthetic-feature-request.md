[SYNTHETIC FEATURE REQUEST — created by the demo executor; no real author supplied or approved it]

Build an independent task board with two lists: To do and Done. Seed it with two original tasks. A user can select one task in To do and move it to Done. Keep the Move selected button disabled when no task is selected. Move only the selected task; keep the other task in To do. Save the change so both lists remain correct after a page reload.

Show the behavior with a frontend component test, an API test that checks both database rows, and a browser test that uses the real frontend, API, and database, then reloads the page. Run the tests before implementation and keep the failing result. Implement the smallest change, run the same checks again, and report the exact commands and results.

For a later change that changes this behavior, route the decision through a trusted evaluator with a clearly labeled synthetic reviewer fixture. Record a negative decision before a positive decision on the same pull request head. The evaluator must report policy status; it must not create or claim a native GitHub review or real human approval. Block any change that removes a required test.
