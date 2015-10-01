# ZyNOS Notes

As no public information is available for many currently available ZyNOS versions, this will document what is known or speculated.

**DISCLAIMER**: No information herein is stated to be true. Use at your own risk. Information contained herein is for educational or research use only. It doesn't make me happy to write this, but that's the world we live in.

## What is ZyNOS?

As the [Wikipedia page](https://en.wikipedia.org/wiki/ZyNOS) states: "[it] is a contraction of ZyXEL and Network Operating System (NOS)".

## Which devices have ZyNOS-based firmware?

Quite a lot, actually, and not only ZyXEL branded ones. Apparently, ZyNOS code is available for licensed use in e.g. SDKs for ADSL chipsets, as can be see with say Trendchip.

## Have they any versioning?

They indeed do. I have observed the following ZyNOS versions as marked in ZyXEL firmware packages:

* 2.50 -- found in old devices like P-782
* 3.40 -- the most popular in ADSL routers
* 3.60
* 3.70
* 3.80
* 3.90
* 4.00 -- for e.g. ZyXEL GS2200

It is currently unknown to me which features are added or removed with each version.

### ZyXEL firmware versioning schema

It is worthy to take notes on firmware versioning schema adopted by ZyXEL (albeit undocumented). Versions have format like `3.60(TX.0)C0` or `3.40(FN.0)C0` and obviously consists of 3 parts.

* Part 1: ZyNOS version, I assume, or that part of the OS that is device-independent. In the two cases above, it is 3.60 and 3.40.
* Part 2: Device-dependent code version. The letters stay the same across the devices, while the digit changes with versions, resetting to zero with each ZyNOS code update.
* Part 3: Unknown; could be configuration or documentation changes only. At least in one case, firmware binaries compared equal (`370TX0C0` and `370TX0C1`).

Note: Firmware released by ZyXEL has the version identified compiled in _BootExtension_.

## On firmware structure

Every ZyNOS-running device posesses a ROM chip containing the firmware image. Typically, this chip is mapped into memory space starting at `BFC00000` (on MIPS-based devices), but that is subject to a specific platform.

The image is divided into sections or _objects_. The mapping of objects to addresses in ROM is achieved via the _memory mapping table_, which itself is stored in ROM. The table stores at least the object's name, starting address, size, and type. Note the table maps both ROM and RAM memory sections, so it is possible to figure out memory configuration of the whole device, not only ROM.

RAM object contents are never contained within update image -- quite obviously.

### Memory mapping and objects

All inspected devices so far contain at least these objects: `MemMapT`, `BootBas`, `BootExt`, `RasCode`, `RomDefa`, `termcap`.

The `MemMapT` object maps the memory mapping table -- its actual location and size in ROM.

The `BootBas` object maps the _BootBase_ code -- the initial program loader for the device. It is not actually contained within the firmware update image, but I have seen a few firmware releases from ZyXEL that contain _BootBase_ update in a separate file. Apart from boot code, _BootBase_ contains vendor and model names. _BootBase_ is rather small, typically 16K, but then, it does not need to do much except loading stage 2.

The `BootExt` object maps the _BootExtension_ code -- stage 2 program loader. It also contains rudimentary debugging facilities allowing to recover the device in case of e.g. problems with configuration. _BootExtension_ is responsible to load actual ZyNOS code.

The `RasCode` object contains the OS image -- the final stage.

The `RomDefa` object contains ROMFILE with default configuration settings. 

The `termcap` object contains what looks like, well, termcap description. I am not sure this is _actually_ used anywhere in code.

