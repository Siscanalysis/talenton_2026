# Supplier questions, and a draft quotation request

**Status: NOT SENT. No supplier has been contacted.**

Prepared 8 September 2026. Nothing in this file may be sent without explicit human
authorisation. It exists so that, if and when someone does make contact, the questions are
the ones that actually close the gaps in `research/sensors/sensor_matrix.md`, rather than
the ones that are easy to ask.

---

## 1. Questions that would close a specific recorded gap

Each question names the record it resolves. A question that resolves nothing is not on
this list.

### Blocking, in order of value

1. **S-14, Unisense.** Can a MiniChamber Lander incubation be sub-sampled for water during
   the incubation, and what is the enclosed chamber area and volume? Without the area, no
   areal flux can be computed at all. Has anyone used the system with laboratory analysis
   of trace metals rather than the supplied microsensors, and if so what contamination
   controls were needed for Pb and Hg at sub-microgram-per-litre levels?
2. **S-14, Unisense.** What is the documented effect of chamber enclosure on porewater
   advection through the enclosed patch? Our layer model is advection-dominated, so a
   chamber that suppresses seepage would systematically under-report the flux we are
   trying to measure.
3. **S-09, Idronaut.** Is the VIP system currently orderable? The company website could
   not be reached on 2026-09-08 owing to a TLS certificate verification error. What is the
   supported analyte list, and is mercury an analyte or only the electrode material?
4. **S-09, Idronaut.** For lead in unmodified seawater at the salinity and pH of a coastal
   site: what is the quantification limit, what is the measurement cycle time, what
   fraction is reported, how often must the mercury film be replated, and what is the
   maximum unattended deployment duration with the antifouling membrane in place?
5. **S-13, DGT Research.** Is a mercury-specific DGT binding layer available, and if so
   which one? The LSPM-NP page lists cationic metals including Pb but not Hg. What
   deployment durations are recommended for sediment in full-strength seawater, and are
   there published salinity limits for the Chelex binding layer?
6. **S-15, Rhizosphere Research Products.** Are there published trace-metal blank data for
   Rhizon CSS samplers, specifically for Pb and Hg, including adsorptive loss and leaching
   from the polymer and the luer fitting?

### Interface and integration

7. **S-05, S-06, S-07, Aqualabo.** Please supply the Modbus register maps: register
   addresses, function codes, data types, byte and word order, scaling factors and units,
   for the CTZN, PHEHT and NTU sensors. **What is the maximum deployment depth in metres
   for each, as distinct from the IP68 rating?**
8. **S-08, nke Instrumentation.** Which WiMo sensors are currently available for MoSens,
   what is the MoSens maximum deployment depth, and can the Modbus register map and the
   user manual be supplied under a non-disclosure agreement if necessary?
9. **S-01, Nortek.** Which output message formats are available on RS-422, what coordinate
   convention is used, and is the integrator guide with the binary format definition
   available? What is the realistic endurance in months for an hourly averaged single-point
   deployment on each battery option?
10. **S-02, Sonardyne.** Is there a lower-frequency-independent variant of the Origin
    platform suitable for a water column under 20 m, and what exactly does the Origin SDK
    give access to: raw pings, processed profiles, or only configuration?
11. **S-17, Blueye.** What is the licence of the published Python SDK, what does it give
    access to (telemetry, video stream, guest-port payloads, mission scripting), and is
    there a documented offline mode with no cloud dependency?

### Analytical route

12. **S-10, Metrohm.** Application Bulletin 438/1 leaves the spiked sea-water lead result
    blank and states the method is best suited to tap and mineral water. **Is there a
    Metrohm application bulletin with a validated sea-water lead determination, and what
    are its limit of detection, recovery and matrix conditions?**
13. **S-11, Milestone.** For the DMA-80 evo: what concentration limit of detection is
    achievable for total mercury in (a) a loaded sorbent solid and (b) a filtered
    sea-water sample, and what sample mass or volume does each assume? Is preconcentration
    required for sea water at ambient levels?
14. **S-12, P S Analytical.** Every published route to the product pages returned HTTP 403
    on 2026-09-08. Is the PSA 10.035 Millennium Merlin a current product? What is the
    validated matrix for the quoted detection limit, and what sample preparation,
    preservation and clean-hands protocol does that limit assume?

### Service and cost

15. **S-18, Subsea Tech.** Has the company performed inspection work on contaminated
    sediment or on a remediation cap? What is a typical day rate and mobilisation cost for
    a two-day ROV condition survey of a hundred-metre-scale seabed area in French coastal
    waters, and what positioning accuracy is achievable for repeat surveys of the same
    tiles?
16. **All suppliers.** Is a loan, rental or demonstration trial available before purchase,
    and is a dated example data export available so that an ingestion adapter can be
    written against real output rather than a guess?

### Questions we must ask ourselves, not a supplier

17. What is the uncapped control patch, where is it, and who authorises it? Without it,
    attenuation is not measurable (`measurement_chain.md` section 3.1).
18. Who holds the permit under OSPAR Annex II Article 5, and what does the authorisation
    require in terms of monitoring and removal? (`research/materials/regulatory_and_monitoring_context.md`)
19. What is the disposal route for retrieved media loaded with Pb and Hg, and what does it
    cost per kilogram? `CostConfig.used_media_handling_eur_per_kg = 12.0` is an assumption
    with no basis.

---

## 2. Draft quotation request

**MARKED NOT SENT. DO NOT SEND WITHOUT EXPLICIT HUMAN AUTHORISATION.**

The draft deliberately contains no site name, no coordinates, no reference to munitions
and no commitment to purchase. Placeholders are in angle brackets.

```text
Subject: Technical enquiry and indicative quotation request: <instrument or service>

Dear <supplier>,

We are carrying out a feasibility study for a monitoring programme over a small
contaminated seabed area in European coastal waters, at a water depth of the order of
<depth> metres, in full-strength seawater. The programme concerns dissolved lead and
mercury and the physical condition of a thin sorbent layer laid on the seabed. At this
stage we are assembling technical evidence, not placing an order.

We would be grateful for the following, and we would rather have an explicit "not
applicable" or "not measured" than an estimate.

1. Exact model and configuration
   Which exact model, revision and configuration would you propose, and is it currently
   available for order?

2. What the instrument measures
   Which parameters are measured directly, and which are derived? For any chemical
   channel, which operationally defined fraction is reported?

3. Performance in the actual matrix
   What is the limit of detection and the limit of quantification, in which matrix, under
   which method, and with what documented recovery? If the published figures were obtained
   in fresh water or in a laboratory buffer, please say so.

4. Marine deployment
   What is the maximum deployment depth in metres, as distinct from an IP rating? What
   antifouling provision exists, and what is the recommended maximum unattended deployment
   duration in a temperate coastal benthic environment?

5. Duty cycle and endurance
   What is the measurement cycle time, and what is the realistic endurance in months for
   <intended sampling scheme> on each power option?

6. Interfaces
   Which physical interfaces are supported (RS232, RS422, RS485, SDI-12, Ethernet, other)?
   For digital protocols, can the register or message definition be supplied, under a
   non-disclosure agreement if required? Is any application-level interface (HTTP, MQTT,
   REST) provided by the instrument itself, as opposed to by a separate gateway?

7. Software and data
   Which software is supplied? Is there a documented software development kit or library,
   and under what licence? Can a dated example data export be provided so that we can
   write an ingestion adapter against real output?

8. Calibration, consumables and servicing
   What calibration is required, at what interval, and by whom? Which consumables are
   needed, at what cost and lead time? What waste or reagent handling is involved?

9. Evaluation
   Is a loan, rental or demonstration trial available before purchase?

10. Indicative commercial information
    An indicative price for the proposed configuration, an indicative lead time, and an
    indicative annual operating cost. We understand these are indicative and not binding.

We are not requesting a site visit and we are not asking you to specify a solution. We are
collecting technical evidence for a feasibility assessment and will come back to you if
and when the study proceeds.

With thanks,
<name>, <organisation>, <contact>
```

---

## 3. Rules for whoever eventually sends this

1. Do not send it automatically. A human authorises each recipient individually.
2. Do not describe the site. The hotspot in this repository is abstract by construction
   (`AGENTS.md` rule 14), and a real enquiry must not turn it concrete by accident.
3. Do not mention munitions to any supplier. Ever.
4. Record every reply as a dated record in `research/references/evidence.json`, with
   `retrieval_status` set to something that makes clear it came from correspondence rather
   than a public page, and update the `status` field only on the strength of what the
   reply actually says.
5. A supplier's answer is a vendor claim. It becomes `measurement` provenance only when
   there is a dated document behind it, and it never becomes independent validation.
6. Until a dated quotation exists, every euro figure in `CostConfig` stays labelled
   `ProvenanceLabel.ASSUMPTION` (`AGENTS.md` rule 11).
