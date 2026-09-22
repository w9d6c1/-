from pymilvus import MilvusClient, DataType

client = MilvusClient(uri='http://kb-milvus:19530', timeout=30)

for coll in ['coll_internal', 'coll_public']:
    try:
        client.drop_collection(coll)
        print(f'{coll}: dropped')
    except Exception as e:
        print(f'{coll}: {e}')

for name in ['coll_public', 'coll_internal', 'coll_customer']:
    try:
        schema = client.create_schema(auto_id=False, enable_dynamic_field=False)
        schema.add_field('id', DataType.VARCHAR, max_length=100, is_primary=True)
        schema.add_field('vector', DataType.FLOAT_VECTOR, dim=1024)
        schema.add_field('content', DataType.VARCHAR, max_length=65535)
        schema.add_field('doc_id', DataType.INT64)
        schema.add_field('chunk_index', DataType.INT64)
        schema.add_field('scope', DataType.VARCHAR, max_length=20)
        schema.add_field('title', DataType.VARCHAR, max_length=500)
        schema.add_field('source_type', DataType.VARCHAR, max_length=32)
        client.create_collection(name, schema=schema)
        idx = client.prepare_index_params()
        idx.add_index('vector', index_type='IVF_FLAT', metric_type='IP', params={'nlist': 128})
        client.create_index(collection_name=name, index_params=idx)
        client.load_collection(name)
        stats = client.get_collection_stats(name)
        print('{}: created, loaded, rows={}'.format(name, stats['row_count']))
    except Exception as e:
        print('{}: {}'.format(name, e))
