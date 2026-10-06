def test_social_catalog_has_core_platforms():
    from sparkbot.social import catalog
    ids = {item["id"] for item in catalog()}
    assert {"instagram","tiktok","youtube","linkedin","facebook","x","threads","pinterest","reddit","canva"} <= ids
