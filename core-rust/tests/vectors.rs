use hexa60_core::encode_chunked;

#[test]
fn python_vectors_bit_identical() {
    let inputs: Vec<Vec<u8>> = vec![
        vec![],
        (0..1).collect(),
        (0..2).collect(),
        (0..3).collect(),
        (0..5).collect(),
        (0..7).collect(),
        (0..8).collect(),
        (0..9).collect(),
        (0..16).collect(),
        (0..17).collect(),
        vec![0xFF; 8],
        vec![0x00; 8],
        b"hello".to_vec(),
    ];
    let expected = [
        "",
        "00",
        "001",
        "0004J",
        "001JGzg",
        "000Pm5a3k6",
        "001hLPmKy9j",
        "001hLPmKy9j08",
        "001hLPmKy9j0zTEq539SYp",
        "001hLPmKy9j0zTEq539SYp0G",
        "WWT953sgX0F",
        "00000000000",
        "9cd50w7",
    ];
    for (inp, exp) in inputs.iter().zip(expected.iter()) {
        assert_eq!(&encode_chunked(inp), exp);
    }
}
