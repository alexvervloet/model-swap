# Deliberate gaps

Subjects the corpus does not cover, chosen so that a question about them has a
correct answer of "the documents do not say". They are recorded here because a
gap you cannot point at is indistinguishable from a gap you forgot, and the
refusal stratum is only trustworthy if the absence was on purpose.

Nothing in this file is uploaded to the system under test. Only
`corpus/meridian/*.md` is.

| Subject | Why it is plausible to ask | Why it is absent |
|---|---|---|
| Private charter of a vessel | An operator this size usually offers it | Never written; no pricing, no process |
| Onboard wifi | Passengers ask about it constantly | No document mentions connectivity at all |
| Catering, menus, allergens | The Coastal vessels are said to have a cafe | The cafe is mentioned once, in the animals policy, and never described |
| School group supervision ratios | Group bookings are covered, ratios are not | Group policy covers fares and cancellation only |
| Staff parental leave, pay, HR terms | It is an internal document set | The corpus is operational, not HR |
| Drone photography from the deck | A modern policy set usually has a line on it | Not written |
| Freight and haulage contracts | Dangerous goods mentions freight as an alternative | Named as a route out, never described |
| Fuel type, emissions, environmental targets | Increasingly expected of an operator | Absent |
| Travel insurance | Consequential loss is excluded, so it comes up | The exclusion is stated, insurance is not discussed |
| Timetable before March 2024 | The Lachlan withdrawal is dated | No historical timetable is included |

## Near misses, which are the useful cases

These read like gaps and are not. A model that refuses them is wrong, and a
model that answers them from the wrong document is also wrong.

| Question | Looks absent because | Actually answerable from |
|---|---|---|
| Can I take a dog to Rensley Point? | No pet policy names Rensley Point | Animals, which says pets travel on the Kilmore route only |
| Is the Harbour Circular wheelchair accessible? | Reads like an accessibility gap | Accessibility, which states plainly that it is not |
| How many bikes fit on the Ashcombe sailing? | The bicycle policy defers to the fleet register | Fleet register, twenty racks per Estuary vessel |
| What happens if the crew are short? | Sounds like an HR question | Crewing, which makes it an operator cancellation |
| Can I get a refund on a Saver if you cancel? | The fare table says Saver never refunds | Disruption, which overrides the fare class |
