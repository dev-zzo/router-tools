# TR-069 ToolSet

This is a tool set designed to take advantage of the flawed TR-069 (CPE WAN Management Protocol) implementations.

## Primer

> The CPE WAN (CWMP) Management Protocol, published by The Broadband Forum as TR-069, 
> specifies a standard communication mechanism for the remote management of end-user devices. 
> It defines a protocol for the secure auto-configuration of a TR-069 device and 
> incorporates other management functions into a common framework. This protocol 
> simplifies device management by specifying the use of an auto configuration server 
> (ACS) to perform remote, centralized management of customer premises equipment (CPE).

Or so they say.

The protocol is SOAP/HTTP at TCP port 7547 (CPE side).

According to the specification, the only reason a CPE is listening on that port is to serve the ACS connection request.

