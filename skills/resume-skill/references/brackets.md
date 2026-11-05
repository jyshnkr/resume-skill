# Platform brackets (rule 11)

A bracket tells a reader that you used an equivalent of a platform the posting names. Use one only when all of this is true:

- the posting names a platform you have not used (for example Azure, GCP, OCI, Kafka) as one the role uses, not as an analogy;
- you used a real equivalent, and the bullet already names it (for example the AWS service);
- the bullet is in a tailoring, never in a version, the bank, a summary or a skills line.

## Form
Right after the AWS service, one per bullet, written `(<Platform>-style)`:

`... through Amazon SQS (Azure Service Bus-style) queues ...`

The bullet must still pass `check.py` (word and character limits include the bracket) and must keep its bank bullet's other words. `validate.py` accepts a bracket-only difference from the bank text without a rewording note.

## Do not
- Do not use a bracket for something the user did not do or used only as a comparison.
- Do not stack two brackets in a bullet.
- Do not add a platform term to a skills line this way (rule 26).
