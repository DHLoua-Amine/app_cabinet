# Licences — how to sell and activate

*Internal. Not for clients.*

## The one rule

**`tools/zarai_licence_key.pem` is the business.** Whoever holds it can mint
valid licences for every installation you have ever shipped. Losing it means you
can never issue another licence for those installations — you would have to
generate a new key, rebuild, and reinstall for every existing client.

- Back it up offline (USB in a drawer, encrypted archive).
- It is git-ignored and absent from the build. Verified.
- Never email it, never put it in the `dist` folder.

## First time only — already done

```bash
python tools/make_licence.py --init
```

Creates the private key and prints the public half, which is already pasted into
`core/licensing.py` as `PUBLIC_KEY_B64`. **Do not run `--init` again.** Every
licence you have issued was signed with the current key; replacing it invalidates
all of them.

## Selling to a client

1. Install the app on the client's machine and let it run.
2. **Paramètres → §10 Licence** shows their **Identifiant machine**, e.g.
   `55A9-D661-5FAD`. They read it to you, or press *Copier*.
   (You can also get it without opening the app: `CabinetNotarialZarai.exe --selftest`
   prints `MACHINE ID = …` and writes it to `selftest.log`.)
3. On your machine:

```bash
python tools/make_licence.py --machine 55A9-D661-5FAD --office "Maitre Ben Salah, Sousse"
```

4. Send them the single `ZARAI-LIC-1.…` line. They paste it into
   **Paramètres → §10 → Clé de licence** and press **Activer**.

Every issue is appended to `tools/issued_licences.log` — your record of who has
what.

### Subscriptions

Add an expiry to sell a yearly renewal instead of a perpetual licence:

```bash
python tools/make_licence.py --machine 55A9-D661-5FAD \
    --office "Maitre Ben Salah, Sousse" --expires 2027-12-31
```

Omit `--expires` for perpetual.

## Two machines in one office

Licences are **per machine**, not per office. An office running a server plus a
workstation needs **two licences** — issue both as part of the one sale. Each
machine shows its own Machine ID in Paramètres.

Watch for this: a workstation left on its 30-day trial keeps working for a month
and then blocks new work, even though the office paid. Activate both machines at
install time.

## What happens without a licence

| State | New records | Existing records |
|---|---|---|
| Trial (30 days) | allowed | allowed |
| Active licence | allowed | allowed |
| Expired / invalid / wrong machine | **blocked** | **allowed** |

**An unlicensed installation never blocks the office from its own deeds.** They
can open, read, correct, print and export everything they have already created.
Only the creation of new clients, dossiers, charges and salaries stops.

This is deliberate. Those are legal documents; holding them hostage over a
billing dispute would be indefensible, and it is not necessary — an office that
cannot open a new dossier calls you the same morning.

## When a client changes hardware

The Machine ID is derived from Windows' MachineGuid and the system disk serial.
It changes if they **reinstall Windows** or **replace the system disk**. Their old
licence stops matching and shows *"Cette licence appartient à une AUTRE machine"*.

That is not a lockout — they can still reach all their data. Ask for the new
Machine ID and issue a replacement licence free of charge. Note it in
`issued_licences.log` so a single office does not quietly become five.

## What this does and does not stop

**Stops:** a client copying the `dist` folder to a colleague's machine, or
reselling a copy. The licence simply will not activate there.

**Does not stop:** someone who decompiles the build and patches the check out.
This is a PyInstaller application; its bytecode is extractable. No local licensing
can survive a determined attacker, and anything claiming otherwise is marketing.

That is an acceptable trade because of who your customers are: licensed notaries,
publicly named and professionally regulated, with far more to lose than the price
of your software. The realistic threat is casual sharing, and casual sharing is
exactly what machine binding stops.

Your strongest protection is not technical: a per-office written contract naming
the notary, and making the ongoing value be support, updates and data migration —
things a pirated copy does not come with.
