from bpx.public import Public

public = Public()
rates = public.get_funding_interval_rates(symbol="SOL_USDC_PERP")

print(rates)