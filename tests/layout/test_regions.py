from src.etl.layout.regions import Region, RegionType, TextUnit

def test_region_orders_and_serializes():
    r = Region(type=RegionType.BODY, bbox=(0, 0, 10, 20), reading_order=1, meta={})
    assert r.type.value == "body"
    assert r.bbox == (0, 0, 10, 20)
    # regions sort by reading_order
    regs = [Region(RegionType.SIDEBAR, (0,0,1,1), 2, {}), Region(RegionType.BODY, (0,0,1,1), 1, {})]
    assert [x.reading_order for x in sorted(regs, key=lambda z: z.reading_order)] == [1, 2]

def test_textunit_holds_region_type():
    u = TextUnit(region_type=RegionType.INFO_BOX, text="Em có biết", reading_order=3, bbox=(1,2,3,4))
    assert u.region_type is RegionType.INFO_BOX
    assert u.text == "Em có biết"
